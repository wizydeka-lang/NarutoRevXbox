# naruto_revolution - ReXGlue Recompiled Project
#
# SDK boilerplate lives in generated/rexglue.cmake.

cmake_minimum_required(VERSION 3.25)
project(naruto_revolution LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/assets/Default.xex")
    message(FATAL_ERROR "Place your extracted Xbox 360 game in assets/ (Default.xex required).")
endif()

include(generated/rexglue.cmake)

# Sources
set(NARUTOREVOLUTION_SOURCES
    src/main.cpp
    src/battle_memory.cpp
    src/render_probe.cpp
    src/frame_capture.cpp
    src/native_view.cpp
    src/texture_decode.cpp
    src/shader_library.cpp
    src/hud_layout.cpp
)

if(WIN32)
    add_executable(naruto_revolution WIN32 ${NARUTOREVOLUTION_SOURCES})
else()
    add_executable(naruto_revolution ${NARUTOREVOLUTION_SOURCES})
endif()

rexglue_setup_target(naruto_revolution GPU_PLUGINS xenos)

# Put the SDK runtime next to the executable, which finds it through its
# $ORIGIN runpath, so the game starts without LD_LIBRARY_PATH (as from Charge).
add_custom_command(TARGET naruto_revolution POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_FILE:rex::runtime>" "$<TARGET_FILE_DIR:naruto_revolution>"
    VERBATIM)

if(NOT EXISTS "${CMAKE_CURRENT_BINARY_DIR}/naruto_revolution.toml")
    configure_file(config/naruto_revolution-performance.toml
        "${CMAKE_CURRENT_BINARY_DIR}/naruto_revolution.toml" COPYONLY)
endif()

find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)
set(REVOLUTION_DISPATCH_CHECK
    "${Python3_EXECUTABLE}" -B
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_function_dispatch.py"
    --manifest "${CMAKE_CURRENT_SOURCE_DIR}/naruto_revolution_manifest.toml"
    --registration "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/naruto_revolution_register.cpp")
add_custom_target(naruto_revolution_check_dispatch
    COMMAND ${REVOLUTION_DISPATCH_CHECK}
    DEPENDS naruto_revolution_codegen
    VERBATIM)
add_dependencies(naruto_revolution naruto_revolution_check_dispatch)
if(TARGET naruto_revolution_recomp)
    add_dependencies(naruto_revolution_recomp naruto_revolution_check_dispatch)
endif()
add_custom_command(TARGET naruto_revolution POST_BUILD
    COMMAND ${REVOLUTION_DISPATCH_CHECK}
        --binary "$<TARGET_FILE:naruto_revolution>" --nm "${CMAKE_NM}"
    VERBATIM)
set_property(TARGET naruto_revolution APPEND PROPERTY LINK_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_function_dispatch.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/naruto_revolution_manifest.toml")
