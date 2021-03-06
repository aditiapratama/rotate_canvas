bl_info = {
    "name": "Rotate Canvas",
    "description": "Rotate camera if in cam view, view if in free navigation",
    "author": "Samuel Bernou, Christophe Seux",
    "version": (1, 0, 3),
    "blender": (2, 83, 0),
    "location": "Shortcut ctrl + alt + right-mouse-click",
    "warning": "",
    "doc_url": "https://github.com/Pullusb/rotate_canvas",
    "category": "3D View"
}

import bpy
import math
import mathutils
from bpy_extras.view3d_utils import location_3d_to_region_2d
from bpy.props import BoolProperty, EnumProperty
## draw utils
import gpu
import bgl
import blf
from gpu_extras.batch import batch_for_shader
from gpu_extras.presets import draw_circle_2d


def draw_callback_px(self, context):
    # 50% alpha, 2 pixel width line
    shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
    bgl.glEnable(bgl.GL_BLEND)
    bgl.glLineWidth(2)

    # init
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": [self.center, self.initial_pos]})#self.vector_initial
    shader.bind()
    shader.uniform_float("color", (0.5, 0.5, 0.8, 0.6))
    batch.draw(shader)

    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": [self.center, self.pos_current]})
    shader.bind()
    shader.uniform_float("color", (0.3, 0.7, 0.2, 0.5))
    batch.draw(shader)

    # restore opengl defaults
    bgl.glLineWidth(1)
    bgl.glDisable(bgl.GL_BLEND)

    ## text
    font_id = 0
    ## draw text debug infos
    blf.position(font_id, 15, 30, 0)
    blf.size(font_id, 20, 72)
    blf.draw(font_id, f'angle: {math.degrees(self.angle):.1f}')


class RC_OT_RotateCanvas(bpy.types.Operator):
    bl_idname = 'view3d.rotate_canvas'
    bl_label = 'Rotate Canvas'
    bl_options = {"REGISTER", "UNDO"}

    def get_center_view(self, context, cam):
        '''
        https://blender.stackexchange.com/questions/6377/coordinates-of-corners-of-camera-view-border
        Thanks to ideasman42
        '''

        frame = cam.data.view_frame()
        mat = cam.matrix_world
        frame = [mat @ v for v in frame]
        frame_px = [location_3d_to_region_2d(context.region, context.space_data.region_3d, v) for v in frame]
        center_x = frame_px[2].x + (frame_px[0].x - frame_px[2].x)/2
        center_y = frame_px[1].y + (frame_px[0].y - frame_px[1].y)/2

        return mathutils.Vector((center_x, center_y))

    def execute(self, context):
        if self.hud:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            context.area.tag_redraw()
        if self.in_cam:
                self.cam.rotation_mode = self.org_rotation_mode
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE'}:
            # Get current mouse coordination (region)
            self.pos_current = mathutils.Vector((event.mouse_region_x, event.mouse_region_y))
            # Get current vector
            self.vector_current = (self.pos_current - self.center).normalized()
            # Calculates the angle between initial and current vectors
            self.angle = self.vector_initial.angle_signed(self.vector_current)#radian
            # print (math.degrees(self.angle), self.vector_initial, self.vector_current)

            if self.in_cam:
                self.cam.matrix_world = self.cam_matrix
                self.cam.rotation_euler.rotate_axis("Z", self.angle)
            
            else:#free view
                context.space_data.region_3d.view_rotation = self._rotation
                rot = context.space_data.region_3d.view_rotation
                rot = rot.to_euler()
                rot.rotate_axis("Z", self.angle)
                context.space_data.region_3d.view_rotation = rot.to_quaternion()
        
        if event.type in {'RIGHTMOUSE', 'LEFTMOUSE', 'MIDDLEMOUSE'} and event.value == 'RELEASE':
            if not self.angle:
                # self.report({'INFO'}, 'Reset')
                aim = context.space_data.region_3d.view_rotation @ mathutils.Vector((0.0, 0.0, 1.0))#view vector
                context.space_data.region_3d.view_rotation = aim.to_track_quat('Z','Y')#track Z, up Y
            self.execute(context)
            return {'FINISHED'}
        
        if event.type == 'ESC':#Cancel
            self.execute(context)
            if self.in_cam:
                self.cam.matrix_world = self.cam_matrix
            else:
                context.space_data.region_3d.view_rotation = self._rotation
            return {'CANCELLED'}


        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        self.hud = get_addon_prefs().canvas_use_hud
        self.angle = 0.0
        self.in_cam = context.region_data.view_perspective == 'CAMERA'

        if self.in_cam:
            # Get camera from scene
            self.cam = bpy.context.scene.camera
            
            #return if one element is locked (else bypass location)
            if self.cam.lock_rotation[:] != (False, False, False):
                self.report({'WARNING'}, 'Camera rotation is locked') 
                return {'CANCELLED'}

            self.center = self.get_center_view(context, self.cam)
            # store original rotation mode
            self.org_rotation_mode = self.cam.rotation_mode
            # set to euler to works with quaternions, restored at finish
            self.cam.rotation_mode = 'XYZ'
            # store camera matrix world
            self.cam_matrix = self.cam.matrix_world.copy()
            # self.cam_init_euler = self.cam.rotation_euler.copy()

        else:
            self.center = mathutils.Vector((context.area.width/2, context.area.height/2))
            
            # store current rotation
            self._rotation = context.space_data.region_3d.view_rotation.copy()

        # Get current mouse coordination
        self.pos_current = mathutils.Vector((event.mouse_region_x, event.mouse_region_y))
        
        self.initial_pos = self.pos_current# for draw debug, else no need
        # Calculate inital vector
        self.vector_initial = self.pos_current - self.center
        self.vector_initial.normalize()
        
        # Initializes the current vector with the same initial vector.
        self.vector_current = self.vector_initial.copy()
        
        args = (self, context)
        if self.hud:
            self._handle = bpy.types.SpaceView3D.draw_handler_add(draw_callback_px, args, 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


### --- PREFS

def auto_rebind(self, context):
    unregister_keymaps()
    register_keymaps()


class RC_prefs(bpy.types.AddonPreferences):
    bl_idname = __name__

    ## Use HUD
    canvas_use_hud: BoolProperty(
        name = "Use Hud",
        description = "Display angle lines and angle value as text on viewport",
        default = False)

    ## Canvas rotate
    canvas_use_shortcut: BoolProperty(
        name = "Use Default Shortcut",
        description = "Use default shortcut: mouse double-click + modifier",
        default = True,
        update=auto_rebind)

    mouse_click : EnumProperty(
        name="Mouse button", description="click on right/left/middle mouse button in combination with a modifier to trigger alignement",
        default='RIGHTMOUSE',
        items=(
            ('RIGHTMOUSE', 'Right click', 'Use click on Right mouse button', 'MOUSE_RMB', 0),
            ('LEFTMOUSE', 'Left click', 'Use click on Left mouse button', 'MOUSE_LMB', 1),
            ('MIDDLEMOUSE', 'Mid click', 'Use click on Mid mouse button', 'MOUSE_MMB', 2),
            ),
        update=auto_rebind)
    
    use_shift: BoolProperty(
            name = "combine with shift",
            description = "add shift",
            default = False,
            update=auto_rebind)

    use_alt: BoolProperty(
            name = "combine with alt",
            description = "add alt",
            default = True,
            update=auto_rebind)

    use_ctrl: BoolProperty(
            name = "combine with ctrl",
            description = "add ctrl",
            default = True,
            update=auto_rebind)

    def draw(self, context):
        layout = self.layout## random color
        
        layout.prop(self, 'canvas_use_hud')
        box = layout.box()
        box.label(text='Shortcut options:')

        box.prop(self, "canvas_use_shortcut", text='Bind shortcuts')

        if self.canvas_use_shortcut:
            
            row = box.row()
            row.label(text="(Auto rebind when changing shortcut)")#icon=""
            # row.operator("prefs.rebind_shortcut", text='Bind/Rebind shortcuts', icon='FILE_REFRESH')#EVENT_SPACEKEY
            row = box.row(align = True)
            row.prop(self, "use_ctrl", text='Ctrl')#, expand=True
            row.prop(self, "use_alt", text='Alt')#, expand=True
            row.prop(self, "use_shift", text='Shift')#, expand=True
            row.prop(self, "mouse_click",text='')#expand=True

            if not self.use_ctrl and not self.use_alt and not self.use_shift:
                box.label(text="Choose at least one modifier to combine with click (default: Ctrl+Alt)", icon="ERROR")# INFO

        else:
            layout.label(text="No hotkey has been set automatically. Following operators needs to be set manually:", icon="ERROR")
            layout.label(text="view3d.rotate_canvas")


### --- KEYMAP

def get_addon_prefs():
    import os
    addon_name = os.path.splitext(__name__)[0]
    addon_prefs = bpy.context.preferences.addons[addon_name].preferences
    return (addon_prefs)

addon_keymaps = []
def register_keymaps():
    pref = get_addon_prefs()
    if not pref.canvas_use_shortcut:
        return
    addon = bpy.context.window_manager.keyconfigs.addon

    km = bpy.context.window_manager.keyconfigs.addon.keymaps.get("3D View")
    if not km:
        km = addon.keymaps.new(name = "3D View", space_type = "VIEW_3D")# valid only in 3d view
    
    if 'view3d.rotate_canvas' not in km.keymap_items:
        km = addon.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new('view3d.rotate_canvas',
        type=pref.mouse_click, value="PRESS", alt=pref.use_alt, ctrl=pref.use_ctrl, shift=pref.use_shift, any=False)
        ## hardcoded
        # kmi = km.keymap_items.new('view3d.rotate_canvas', 'MIDDLEMOUSE', 'PRESS', ctrl=True, shift=False, alt=True)# ctrl + alt + mid mouse
        # kmi = km.keymap_items.new('view3d.rotate_canvas', type='RIGHTMOUSE', value="PRESS", alt=True, ctrl=True, shift=False, any=False)# ctrl + alt + right mouse
        addon_keymaps.append(km)

def unregister_keymaps():
    for km in addon_keymaps:
        for kmi in km.keymap_items:
            km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    # del addon_keymaps[:]

### --- REGISTER

canvas_classes = (
RC_prefs, 
RC_OT_RotateCanvas, 
)

def register():
    if not bpy.app.background:
        for cls in canvas_classes:
            bpy.utils.register_class(cls)

        register_keymaps()


def unregister():
    if not bpy.app.background:
        unregister_keymaps()

        for cls in reversed(canvas_classes):
            bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()