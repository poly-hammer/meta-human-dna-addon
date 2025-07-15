# Textures

## Importing Textures
When importing or converting a mesh to/from a DNA file, you are given an extra option to specify the `Maps` folder location. By default, if a `Maps` folder exists alongside the `.dna` file, the importer will use that, otherwise you can explicitly set the `Maps` folder to your desired location.

![](./images/textures/1.png){: class="rounded-image center-image" style="width:500px"}
![](./images/textures/2.png){: class="rounded-image center-image" style="width:500px"}

The importer will link any `.tga` or `.png` textures to the [Texture Logic](./terminology.md#texture-logic) node inputs that follow these patterns:

### Pattern 1
```
Head_Basecolor.png  -> Color_MAIN
Head_Basecolor_Animated_CM1.png -> Color_CM1
Head_Basecolor_Animated_CM2.png -> Color_CM2
Head_Basecolor_Animated_CM3.png -> Color_CM3
Head_Normal.png -> Normal_MAIN
Head_Normal_Animated_WM1.png -> Normal_WM1
Head_Normal_Animated_WM2.png -> Normal_WM2
Head_Normal_Animated_WM3.png -> Normal_WM3
```

### Pattern 2
```
Color_MAIN.tga -> Color_MAIN
Color_CM1.tga -> Color_CM1
Color_CM2.tga -> Color_CM2
Color_CM3.tga -> Color_CM3
Normal_MAIN.tga -> Normal_MAIN
Normal_WM1.tga -> Normal_WM1
Normal_WM2.tga -> Normal_WM2
Normal_WM3.tga -> Normal_WM3
```
### Pattern 3
```
head_color_map.tga -> Color_MAIN
head_cm1_color_map.tga -> Color_CM1
head_cm2_color_map.tga -> Color_CM2
head_cm3_color_map.tga -> Color_CM3
head_normal_map.tga -> Normal_MAIN
head_wm1_normal_map.tga -> Normal_WM1
head_wm2_normal_map.tga -> Normal_WM2
head_wm3_normal_map.tga -> Normal_WM3
```

## Custom Materials in Blender
You can make a totally custom material node tree if you want. All you need to do is add a single
[Texture Logic](./terminology.md#texture-logic) node to the graph, then link your material in the [Rig Logic Instance](./terminology.md#rig-logic-instance) outputs.

![](./images/textures/3.gif){: class="rounded-image center-image"}

With this set, now [RigLogic](./terminology.md#riglogic) will update the wrinkle map masks for you as the GUI controls are evaluated.