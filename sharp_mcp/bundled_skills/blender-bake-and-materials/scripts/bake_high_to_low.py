"""Automated High-to-Low Poly Texture Baker for Blender Cycles.
Bakes Tangent Space Normal and Ambient Occlusion maps to image files.
"""
import bpy
import os

def bake_high_to_low(
    high_obj: bpy.types.Object,
    low_obj: bpy.types.Object,
    output_dir: str,
    base_name: str,
    resolution: int = 1024,
    ray_dist: float = 0.05
):
    os.makedirs(output_dir, exist_ok=True)
    scene = bpy.context.scene

    # 1. Setup Cycles for Baking
    scene.render.engine = 'CYCLES'
    try:
        scene.cycles.device = 'GPU'
    except Exception:
        scene.cycles.device = 'CPU'
    scene.cycles.bake_type = 'NORMAL'
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.cage_extrusion = ray_dist

    # 2. Prepare Low-Poly Material and Image Texture Node
    mat = low_obj.active_material
    if not mat:
        mat = bpy.data.materials.new(name=f"M_{base_name}_Bake")
        mat.use_nodes = True
        low_obj.data.materials.append(mat)

    nodes = mat.node_tree.nodes
    bake_node = nodes.new('ShaderNodeTexImage')
    bake_node.name = "BakeTargetNode"

    # --- Bake Normal Map ---
    norm_img = bpy.data.images.new(f"{base_name}_Normal", width=resolution, height=resolution, float_buffer=False)
    norm_img.colorspace_settings.name = 'Non-Color'
    bake_node.image = norm_img
    nodes.active = bake_node

    # Select High then Low (Active)
    bpy.ops.object.select_all(action='DESELECT')
    high_obj.select_set(True)
    low_obj.select_set(True)
    bpy.context.view_layer.objects.active = low_obj

    print(f"Baking Normal Map for {base_name} ({resolution}x{resolution})...")
    bpy.ops.object.bake(type='NORMAL')
    norm_path = os.path.join(output_dir, f"{base_name}_Normal.png")
    norm_img.filepath_raw = norm_path
    norm_img.file_format = 'PNG'
    norm_img.save()

    # --- Bake AO Map ---
    ao_img = bpy.data.images.new(f"{base_name}_AO", width=resolution, height=resolution, float_buffer=False)
    ao_img.colorspace_settings.name = 'Non-Color'
    bake_node.image = ao_img

    print(f"Baking AO Map for {base_name} ({resolution}x{resolution})...")
    bpy.ops.object.bake(type='AO')
    ao_path = os.path.join(output_dir, f"{base_name}_AO.png")
    ao_img.filepath_raw = ao_path
    ao_img.file_format = 'PNG'
    ao_img.save()

    # Clean up bake node
    nodes.remove(bake_node)

    return {
        "normal": norm_path,
        "ao": ao_path,
        "resolution": resolution,
    }

if __name__ == "__main__":
    sel = bpy.context.selected_objects
    if len(sel) >= 2:
        low = bpy.context.active_object
        high = next((o for o in sel if o != low), None)
        if high and low:
            res = bake_high_to_low(high, low, bpy.path.abspath("//textures/"), low.name)
            print("BAKE RESULT:", res)
    else:
        print("Select High-Poly object, then shift-select Low-Poly active object to bake.")
