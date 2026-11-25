#!/usr/bin/env python3
"""
Render Live2D model via OpenGL offscreen.
Supports mask/clipping, blend modes and all GPU rendering features.

Usage:
    python render_gl.py <model3.json> [output.png] [--param ID=VALUE ...]

Examples:
    python render_gl.py model.json ref.png
    python render_gl.py model.json ref.png --param ParamClothSchool=1
"""
import argparse
import os
import sys

import glfw
import OpenGL.GL as gl
from PIL import Image

import live2d.v3 as live2d


def render_gl(model_json_path, output_path, params=None, bg=(0.0, 0.0, 0.0, 0.0)):
    if not glfw.init():
        raise RuntimeError("glfw init failed")

    live2d.init()
    model = live2d.Model()
    model.LoadModelJson(model_json_path)
    canvas_w, canvas_h = map(int, model.GetCanvasSizePixel())
    print(f"canvas: {canvas_w}x{canvas_h}")

    if params:
        for k, v in params.items():
            try:
                model.SetParameterValueById(k, float(v))
                print(f"param: {k} = {v}")
            except Exception as e:
                print(f"warn: cannot set {k}: {e}")
        model.SaveParameters()

    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    window = glfw.create_window(canvas_w, canvas_h, "offscreen", None, None)
    if not window:
        glfw.terminate()
        raise RuntimeError("cannot create GLFW window")
    glfw.make_context_current(window)

    live2d.glInit()
    model.CreateRenderer(maskBufferCount=2)
    model.Resize(canvas_w, canvas_h)

    model.Update(0.0)
    live2d.clearBuffer(*bg)
    model.Draw()

    buf = gl.glReadPixels(0, 0, canvas_w, canvas_h, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE)
    image = Image.frombytes("RGBA", (canvas_w, canvas_h), buf)
    image = image.transpose(Image.FLIP_TOP_BOTTOM)
    image.save(output_path)
    print(f"saved: {output_path}")

    model.DestroyRenderer()
    live2d.glRelease()
    live2d.dispose()
    glfw.destroy_window(window)
    glfw.terminate()


def main():
    parser = argparse.ArgumentParser(description="Render Live2D via OpenGL offscreen")
    parser.add_argument("model", help="model3.json path")
    parser.add_argument("output", nargs="?", default="render_gl.png", help="output PNG path")
    parser.add_argument("--param", action="append", default=[],
                        help="set parameter, format ID=VALUE")
    parser.add_argument("--bg", nargs=4, type=float, default=[0.0, 0.0, 0.0, 0.0],
                        metavar=("R", "G", "B", "A"),
                        help="background color 0.0~1.0, default transparent")
    args = parser.parse_args()

    if not os.path.exists(args.model):
        print(f"error: model not found: {args.model}")
        sys.exit(1)

    params = {}
    for p in args.param:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k] = float(v)
        else:
            print(f"warn: bad param format: {p}")

    try:
        render_gl(args.model, args.output, params, tuple(args.bg))
    except Exception as e:
        print(f"error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
