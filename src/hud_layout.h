// naruto_revolution - HUD layout changes in the native renderer
//
// Moves, resizes or hides parts of the fight HUD by changing their draws'
// viewports; the game itself is unchanged. The HUD is split into groups:
//   p1_status  player 1's portrait, health, chakra and support gauges
//   p2_status  player 2's
//   timer      the round timer between them
//   p1_items   player 1's item slots (the diamond with icons and counts)
//   p2_items   player 2's
// The layout is a list of "group=dx,dy,scale" separated by ';' (or new
// lines), in the game's HUD space (1280 x 640). scale 0 hides the group.
// Groups not named stay where the game puts them. For example
//   p1_items=0,-221,1;p2_items=0,-221,1
// puts both item diamonds under the health bars.
//
// The layout comes from REVOLUTION_HUD_LAYOUT, or from the file named by
// REVOLUTION_HUD_LAYOUT_FILE, which is read again whenever it changes (so an
// editor can change the HUD while the game runs).
//
// A frame is a fight only if it has an item diamond (four sprites with one
// texture, 55 pixels left and right and 49 above and below a centre), and
// only draws in that diamond's pass and viewport move, so menus and the 3D
// scene are never touched.

#pragma once

#include <array>
#include <vector>

#include "native_view.h"

namespace hud_layout {

// x' = x * scale + offset (likewise y), applied to a draw's viewport in its
// own (unscaled) pixels.
struct Transform {
  float scale = 1.0f;
  float x = 0.0f, y = 0.0f;
  bool hidden = false;
};

// One per captured draw; empty when nothing changes this frame.
std::vector<Transform> Transforms(const native_view::FrameInfo& frame);

}  // namespace hud_layout
