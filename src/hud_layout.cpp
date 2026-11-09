// naruto_revolution - HUD layout changes in the native renderer (see hud_layout.h)

#include "hud_layout.h"

#include <sys/stat.h>

#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <mutex>
#include <sstream>
#include <string>

#include <rex/logging.h>

#include "shader_library.h"

namespace hud_layout {
namespace {

enum Group { kP1Status, kP2Status, kTimer, kP1Items, kP2Items, kGroups };

const char* const kNames[kGroups] = {"p1_status", "p2_status", "timer", "p1_items", "p2_items"};
// The point each group is resized around: the middle of its box in the
// editors (tools/launcher, HudEditorActivity).
const float kPivots[kGroups][2] = {{290, 110}, {990, 110}, {640, 92}, {195, 511}, {1085, 511}};

struct Setting {
  float dx = 0, dy = 0, scale = 1;
};

struct Layout {
  Setting groups[kGroups];
  bool any = false;
};

Layout Parse(const std::string& text) {
  Layout layout;
  std::string all = text;
  for (char& c : all) {
    if (c == '\n') {
      c = ';';
    }
  }
  std::istringstream parts(all);
  std::string entry;
  {
    while (std::getline(parts, entry, ';')) {
      size_t eq = entry.find('=');
      if (eq == std::string::npos) {
        continue;
      }
      std::string name = entry.substr(0, eq);
      name.erase(0, name.find_first_not_of(" \t\r"));
      name.erase(name.find_last_not_of(" \t\r") + 1);
      Setting s;
      if (std::sscanf(entry.c_str() + eq + 1, "%f,%f,%f", &s.dx, &s.dy, &s.scale) < 2) {
        continue;
      }
      for (int g = 0; g < kGroups; ++g) {
        if (name == kNames[g]) {
          layout.groups[g] = s;
          layout.any |= s.dx != 0 || s.dy != 0 || s.scale != 1;
        }
      }
    }
  }
  return layout;
}

// The layout in effect, from REVOLUTION_HUD_LAYOUT or REVOLUTION_HUD_LAYOUT_FILE.
Layout Current() {
  static std::mutex mutex;
  static Layout layout;
  static bool started = false;
  static const char* file = nullptr;
  static time_t file_time = 0;
  static std::chrono::steady_clock::time_point next_check;
  std::lock_guard<std::mutex> lock(mutex);
  if (!started) {
    started = true;
    if (const char* text = std::getenv("REVOLUTION_HUD_LAYOUT"); text && *text) {
      layout = Parse(text);
      REXLOG_INFO("[hud] layout: {}", text);
    }
    file = std::getenv("REVOLUTION_HUD_LAYOUT_FILE");
    if (file && !*file) {
      file = nullptr;
    }
  }
  auto now = std::chrono::steady_clock::now();
  if (file && now >= next_check) {
    next_check = now + std::chrono::milliseconds(500);
    struct stat st;
    time_t mtime = ::stat(file, &st) == 0 ? st.st_mtime : 0;
    if (mtime != file_time) {
      file_time = mtime;
      std::ifstream in(file);
      std::stringstream text;
      text << in.rdbuf();
      layout = Parse(text.str());
      REXLOG_INFO("[hud] layout from {}: {}", file, layout.any ? "changed" : "the game's");
    }
  }
  return layout;
}

float F32(const uint8_t* p) {
  float v;
  std::memcpy(&v, p, 4);
  return v;
}

struct Sprite {
  size_t draw;
  float x, y;         // centre (material sprites) or first corner (others)
  uint32_t texture;   // base address word of the first texture, 0 if none
  bool material;      // the 2D material shader (nuccMaterial 0x1800)
  bool quad;          // four indices
};

// Where a HUD draw sits, in viewport pixels.
bool Locate(const native_view::FrameInfo& frame, size_t index, Sprite& out) {
  const native_view::Draw& d = frame.captured[index];
  if (d.vertex_shader < 0 || !d.index_count) {
    return false;
  }
  if (!(d.vte_control & 3) || !(d.vte_control & 12)) {
    return false;
  }
  const auto& shader = shader_library::Shaders()[d.vertex_shader];
  const float* vp = d.viewport;
  out.draw = index;
  out.quad = d.index_count == 4;
  out.texture = d.texture_count ? frame.textures[d.first_texture].fetch[1] & ~0xFFFu : 0;
  if (shader.library == "nuccMaterial" && shader.offset == 0x1800) {
    // Rows c4-c7 place the mesh; c7 is its origin in clip space.
    if (d.vertex_constants + 8 * 16 > frame.data.size()) {
      return false;
    }
    const uint8_t* c7 = frame.data.data() + d.vertex_constants + 7 * 16;
    float w = F32(c7 + 12);
    if (w == 0.0f) {
      return false;
    }
    out.x = vp[1] + vp[0] * (F32(c7) / w);
    out.y = vp[3] + vp[2] * (F32(c7 + 4) / w);
    out.material = true;
    return true;
  }
  if (shader.library == "runtime" && d.binding_count && d.attribute_count) {
    // Screen-space sprites (names, slot counts): x and -y in pixels.
    const native_view::VertexAttribute& a = frame.attributes[d.first_attribute];
    const native_view::VertexBinding& b = frame.bindings[d.first_binding + a.binding];
    const uint8_t* base = b.cached >= 0 ? frame.vertex_data[b.cached]->bytes.data()
                                        : frame.data.data();
    const uint8_t* v = base + b.data_offset + a.offset;
    out.x = F32(v);
    out.y = std::abs(F32(v + 4));
    out.material = false;
    return true;
  }
  return false;
}

bool Near(float a, float b) {
  return std::abs(a - b) < 4.0f;
}

bool SameViewport(const native_view::Draw& a, const native_view::Draw& b) {
  return std::memcmp(a.viewport, b.viewport, sizeof(float) * 4) == 0 &&
         (a.vte_control & 15) == (b.vte_control & 15);
}

}  // namespace

std::vector<Transform> Transforms(const native_view::FrameInfo& frame) {
  const Layout layout = Current();
  if (!layout.any) {
    return {};
  }
  std::vector<Sprite> sprites;
  for (size_t i = 0; i < frame.captured.size(); ++i) {
    Sprite s;
    if (Locate(frame, i, s)) {
      sprites.push_back(s);
    }
  }
  // Item diamonds: four material quads sharing a texture at the four points.
  struct Diamond {
    float x, y;
    size_t draw;
  };
  std::vector<Diamond> diamonds;
  for (const Sprite& top : sprites) {
    if (!top.material || !top.quad || !top.texture) {
      continue;
    }
    float cx = top.x, cy = top.y + 49.0f;
    int found = 0;
    for (const Sprite& s : sprites) {
      if (!s.material || s.texture != top.texture) {
        continue;
      }
      if (Near(s.y, cy) && Near(s.x, cx - 55)) found |= 1;
      if (Near(s.y, cy) && Near(s.x, cx + 55)) found |= 2;
      if (Near(s.y, cy + 49) && Near(s.x, cx)) found |= 4;
    }
    if (found != 7) {
      continue;
    }
    bool seen = false;
    for (const Diamond& d : diamonds) {
      // The icons form a second diamond about 20 pixels from the frames.
      seen |= std::abs(d.x - cx) < 60.0f && std::abs(d.y - cy) < 60.0f;
    }
    if (!seen) {
      diamonds.push_back({cx, cy, top.draw});
    }
  }
  if (diamonds.empty()) {
    return {};
  }
  const native_view::Draw& hud = frame.captured[diamonds[0].draw];
  const float middle = hud.viewport[1];

  std::vector<Transform> transforms(frame.captured.size());
  for (const Sprite& s : sprites) {
    // Only the HUD's own pass: the 3D scene and its full-screen effects use
    // the same viewport.
    if (frame.captured[s.draw].pass != hud.pass || !SameViewport(frame.captured[s.draw], hud)) {
      continue;
    }
    int group = -1;
    for (const Diamond& d : diamonds) {
      // A diamond's slots, icons and counts all lie within ~100 pixels.
      if (std::abs(s.x - d.x) < 105.0f && std::abs(s.y - d.y) < 105.0f) {
        group = d.x < middle ? kP1Items : kP2Items;
      }
    }
    if (group < 0 && s.y < 230.0f) {
      group = s.x < middle - 40.0f ? kP1Status : s.x > middle + 40.0f ? kP2Status : kTimer;
    }
    if (group < 0) {
      continue;
    }
    const Setting& g = layout.groups[group];
    Transform& t = transforms[s.draw];
    if (g.scale <= 0.0f) {
      t.hidden = true;
      continue;
    }
    // Around the group's pivot: x' = p + (x - p) * scale + dx.
    float px = kPivots[group][0] + (middle - 640.0f);
    float py = kPivots[group][1];
    t.scale = g.scale;
    t.x = px * (1.0f - g.scale) + g.dx;
    t.y = py * (1.0f - g.scale) + g.dy;
  }
  static bool logged = false;
  if (!logged) {
    logged = true;
    REXLOG_INFO("[hud] fight HUD found ({} item diamond(s)); applying the layout",
                diamonds.size());
  }
  return transforms;
}

}  // namespace hud_layout
