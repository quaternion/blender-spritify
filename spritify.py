  
# ***** BEGIN GPL LICENSE BLOCK *****
#
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ***** END GPL LICENCE BLOCK *****


bl_info = {
    "name": "Spritify",
    "author": "Jason van Gumster (Fweeb)",
    "version": (0, 6, 4),
    "blender": (2, 80, 0),
    "location": "Render > Spritify",
    "description": "Converts rendered frames into a sprite sheet once render is complete",
    "warning": "Requires ImageMagick",
    "wiki_url": "http://wiki.blender.org/index.php?title=Extensions:2.6/Py/Scripts/Render/Spritify",
    "tracker_url": "https://github.com/FreezingMoon/Spritify/issues",
    "category": "Render"}


import bpy, os, subprocess, math, re
from bpy.app.handlers import persistent
from pathlib import PurePath


class SpriteSheetProperties(bpy.types.PropertyGroup):
    filepath: bpy.props.StringProperty(
        name = "Sprite Sheet Filepath",
        description = "Save location for sprite sheet (should be PNG format)",
        subtype = 'FILE_PATH',
        default = os.path.join(bpy.context.preferences.filepaths.render_output_directory, "sprites.png"))
    imagemagick_path: bpy.props.StringProperty(
        name = "Imagemagick Path",
        description = "Path where the Imagemagick binaries can be found (only on Linux and macOS)",
        subtype = 'FILE_PATH',
        default = '/usr/bin'
    )
    quality: bpy.props.IntProperty(
        name = "Quality",
        description = "Quality setting for sprite sheet image",
        subtype = 'PERCENTAGE',
        max = 100,
        default = 100)
    is_rows: bpy.props.EnumProperty(
        name = "Rows/Columns",
        description = "Choose if tiles will be arranged by rows or columns",
        items = (('ROWS', "Rows", "Rows"), ('COLUMNS', "Columns", "Columns")),
        default = 'ROWS')
    tiles: bpy.props.IntProperty(
        name = "Tiles",
        description = "Number of tiles in the chosen direction (rows or columns)",
        default = 8)
    offset_x: bpy.props.IntProperty(
        name = "Offset X",
        description = "Horizontal offset between tiles (in pixels)",
        default = 2)
    offset_y: bpy.props.IntProperty(
        name = "Offset Y",
        description = "Vertical offset between tiles (in pixels)",
        default = 2)
    bg_color: bpy.props.FloatVectorProperty(
        name = "Background Color",
        description = "Fill color for sprite backgrounds",
        subtype = 'COLOR',
        size = 4,
        min = 0.0,
        max = 1.0,
        default = (0.0, 0.0, 0.0, 0.0))
    auto_sprite: bpy.props.BoolProperty(
        name = "AutoSpritify",
        description = "Automatically create a spritesheet when rendering is complete",
        default = True)
    auto_gif: bpy.props.BoolProperty(
        name = "AutoGIF",
        description = "Automatically create an animated GIF when rendering is complete",
        default = True)
        
def find_bin_path_windows():
    import winreg

    REG_PATH = "SOFTWARE\ImageMagick\Current"
    
    try:
        registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0,
                                       winreg.KEY_READ)
        value, regtype = winreg.QueryValueEx(registry_key, "BinPath")
        winreg.CloseKey(registry_key)
        
    except WindowsError:
        return None
    
    print(value)
    return value


def build_imagepath_template(scene):
    render_filepath = PurePath(scene.render.filepath)
    file_suffix = render_filepath.suffix or scene.render.file_extension

    filename_match = re.match(r"^(.+?)(#+)([^#]*)$", render_filepath.stem)
    if filename_match:
        digits_count = len(filename_match.group(2))
        index_template = "{index:0%dd}{suffix}" % digits_count
        filename_template = filename_match.group(1) + index_template + filename_match.group(3)
    else:
        filename_template = render_filepath.stem + "{index:04d}{suffix}"
    
    filepath_template = render_filepath.with_name(filename_template).with_suffix(file_suffix)
    return filepath_template


def build_image_paths(scene, filepath_template, suffix):
    image_paths = []
    for i in range(scene.frame_start, scene.frame_end + 1, scene.frame_step):
        filepath = str(filepath_template).format(index = i, suffix = suffix)
        image_paths.append(filepath)
    return image_paths    

def build_suffixes(scene):
    suffixes = []
    if scene.render.use_multiview and scene.render.views_format == 'MULTIVIEW':
        for view in scene.render.views:
            suffixes.append(view.file_suffix)
    else:
        suffixes.append('')
    return suffixes

@persistent
def spritify(scene):
    if scene.spritesheet.auto_sprite == True:
        print("Making sprite sheet")        

        if scene.spritesheet.is_rows == 'ROWS':
            tile_setting = str(scene.spritesheet.tiles) + "x"
        else:
            tile_setting = "x" + str(scene.spritesheet.tiles)
            
        suffixes = build_suffixes(scene)
        imagepath_template = build_imagepath_template(scene)
            
        bin_path = scene.spritesheet.imagemagick_path
        if os.name == "nt":
            bin_path = find_bin_pfilenamesath_windows()
            
        out_filepath = PurePath(scene.spritesheet.filepath)
        
        for suffix in suffixes:
            # Preload images
            images = build_image_paths(scene, imagepath_template, suffix)
            
            # Calc number of images per file
            images_count = len(images)
            offset = 0
            index = 0
            
            # Build spritesheet filepath
            spritesheet_filepath = out_filepath.with_name(out_filepath.stem + suffix + out_filepath.suffix)

            # While is faster than for+range
            while offset < images_count:
                current_images = images[offset:offset+images_count]                
                    
                width = scene.render.resolution_x * scene.render.resolution_percentage / 100
                height = scene.render.resolution_y * scene.render.resolution_percentage / 100
                
                if scene.render.use_crop_to_border:
                    width = scene.render.border_max_x * width - scene.render.border_min_x * width
                    height = scene.render.border_max_y * height - scene.render.border_min_y * height
                    
                montage_call = [
                    "%s/montage" % bin_path,
                    "-depth", "8",
                    "-tile", tile_setting,
                    "-geometry", str(width) + "x" + str(height) \
                        + "+" + str(scene.spritesheet.offset_x) + "+" + str(scene.spritesheet.offset_y),
                    "-background", "rgba(" + \
                        str(scene.spritesheet.bg_color[0] * 100) + "%, " + \
                        str(scene.spritesheet.bg_color[1] * 100) + "%, " + \
                        str(scene.spritesheet.bg_color[2] * 100) + "%, " + \
                        str(scene.spritesheet.bg_color[3]) + ")",
                    "-quality", str(scene.spritesheet.quality)
                ]
                montage_call.extend(current_images)
                montage_call.append(bpy.path.abspath(str(spritesheet_filepath)))

                subprocess.call(montage_call)
                offset += images_count
                index += 1


@persistent
def gifify(scene):
    if scene.spritesheet.auto_gif == True:
        print("Generating animated GIF")       

        # If windows, try and find binary
        convert_path = "%s/convert" % scene.spritesheet.imagemagick_path
        
        if os.name == "nt":
            bin_path = find_bin_path_windows()
            
            if bin_path:
                convert_path = os.path.join(bin_path, "convert")

        suffixes = build_suffixes(scene)
        filepath_template = build_imagepath_template(scene)
        
        out_filepath = PurePath(scene.spritesheet.filepath)

        for suffix in suffixes:
            images = build_image_paths(scene, filepath_template, suffix)
            gif_filepath = out_filepath.with_name(out_filepath.stem + suffix).with_suffix('.gif')
        
            subprocess.call([
                convert_path,
                "-delay", "1x" + str(scene.render.fps),
                "-dispose", "background",
                "-loop", "0",
                *images,
                bpy.path.abspath(str(gif_filepath))])


# Operator (just wrapping the handler to make things easy if auto_sprite is False)
class SpritifyOperator(bpy.types.Operator):
    """Generate a sprite sheet from completed animation render"""
    bl_idname = "render.spritify"
    bl_label = "Generate a sprite sheet from a completed animation render"

#    @classmethod
#    def poll(cls, context):
##        if context.scene is not None and len(os.listdir(bpy.path.abspath(context.scene.render.filepath))) > 0: #XXX a bit hacky; an empty dir doesn't necessarily mean that the render has been done
##            return True
##        else:
#        return False

    def execute(self, context):
        toggle = False
        if context.scene.spritesheet.auto_sprite == False:
            context.scene.spritesheet.auto_sprite = True
            toggle = True
        spritify(context.scene)
        if toggle == True:
            context.scene.spritesheet.auto_sprite = False
        return {'FINISHED'}


# Operator (just wraps the handler if auto_gif is False)
class GIFifyOperator(bpy.types.Operator):
    """Generate an animated GIF from completed animation render"""
    bl_idname = "render.gifify"
    bl_label = "Generate an animated GIF from a completed animation render"

#    @classmethod
#    def poll(cls, context):
#        if context.scene is not None and len(os.listdir(bpy.path.abspath(context.scene.render.filepath))) > 0: #XXX a bit hacky; an empty dir doesn't necessarily mean that the render has been done
#            return True
#        else:
#            return False

    def execute(self, context):
        toggle = False
        if context.scene.spritesheet.auto_gif == False:
            context.scene.spritesheet.auto_gif = True
            toggle = True
        gifify(context.scene)
        if toggle == True:
            context.scene.spritesheet.auto_gif = False
        return {'FINISHED'}


# UI

class SpritifyPanel(bpy.types.Panel):
    """UI Panel for Spritify"""
    bl_label = "Spritify"
    bl_idname = "RENDER_PT_spritify"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"

    def draw(self, context):
        layout = self.layout
    
        layout.prop(context.scene.spritesheet, "imagemagick_path")
        layout.prop(context.scene.spritesheet, "filepath")
        box = layout.box()
        split = box.split(factor = 0.5)
        col = split.column()
        col.operator("render.spritify", text = "Generate Sprite Sheet")
        col = split.column()
        col.prop(context.scene.spritesheet, "auto_sprite")
        split = box.split(factor = 0.5)
        col = split.column(align = True)
        col.row().prop(context.scene.spritesheet, "is_rows", expand = True)
        col.prop(context.scene.spritesheet, "tiles")
        sub = col.split(factor = 0.5)
        sub.prop(context.scene.spritesheet, "offset_x")
        sub.prop(context.scene.spritesheet, "offset_y")
        col = split.column()
        col.prop(context.scene.spritesheet, "bg_color")
        col.prop(context.scene.spritesheet, "quality", slider = True)
        box = layout.box()
        split = box.split(factor = 0.5)
        col = split.column()
        col.operator("render.gifify", text = "Generate Animated GIF")
        col = split.column()
        col.prop(context.scene.spritesheet, "auto_gif")
        box.label(text="Animated GIF uses the spritesheet filepath")
        


# Registration

def register():
    bpy.utils.register_class(SpriteSheetProperties)
    bpy.types.Scene.spritesheet = bpy.props.PointerProperty(type = SpriteSheetProperties)
    bpy.app.handlers.render_complete.append(spritify)
    bpy.app.handlers.render_complete.append(gifify)
    bpy.utils.register_class(SpritifyOperator)
    bpy.utils.register_class(GIFifyOperator)
    bpy.utils.register_class(SpritifyPanel)

def unregister():
    bpy.utils.unregister_class(SpritifyPanel)
    bpy.utils.unregister_class(SpritifyOperator)
    bpy.utils.unregister_class(GIFifyOperator)
    bpy.app.handlers.render_complete.remove(spritify)
    bpy.app.handlers.render_complete.remove(gifify)
    del bpy.types.Scene.spritesheet
    bpy.utils.unregister_class(SpriteSheetProperties)

if __name__ == '__main__':
    register()