# Textures

## Importing Textures
When importing or converting a mesh to/from a DNA file, you are given an extra option to specify the `maps` folder location. By default, if a `maps` folder exists alongside the `.dna` file, the importer will use that, otherwise you can explicitly set the `maps` folder to your desired location.

![](../images/textures/1.png){: class="rounded-image center-image" style="width:500px"}
![](../images/textures/2.png){: class="rounded-image center-image" style="width:500px"}

The importer will link any `.tga` or `.png` textures to the [Texture Logic](./terminology.md#texture-logic) node inputs that follow these patterns:

### Pattern 1
```
Color_MAIN.tga -> Color_MAIN
Color_CM1.tga -> Color_CM1
Color_CM2.tga -> Color_CM2
Color_CM3.tga -> Color_CM3
Normal_MAIN.tga -> Normal_MAIN
Normal_WM1.tga -> Normal_WM1
Normal_WM2.tga -> Normal_WM2
Normal_WM3.tga -> Normal_WM3
Cavity_MAIN.tga -> Cavity_MAIN
Roughness_MAIN.tga -> Roughness_MAIN
```
### Pattern 2
```
head_color_map.tga -> Color_MAIN
head_cm1_color_map.tga -> Color_CM1
head_cm2_color_map.tga -> Color_CM2
head_cm3_color_map.tga -> Color_CM3
head_normal_map.tga -> Normal_MAIN
head_wm1_normal_map.tga -> Normal_WM1
head_wm2_normal_map.tga -> Normal_WM2
head_wm3_normal_map.tga -> Normal_WM3
head_cavity_map.tga -> Cavity_MAIN
head_roughness_map.tga -> Roughness_MAIN
```

## Custom Materials in Blender
You can make a totally custom material node tree if you want. All you need to do is add a single
[Texture Logic](./terminology.md#texture-logic) node to the graph, then link your material in the [Rig Logic Instance](./terminology.md#rig-logic-instance) outputs.

![](../images/textures/3.gif){: class="rounded-image center-image"}

With this set, now [RigLogic](./terminology.md#riglogic) will update the wrinkle map masks for you as the GUI control are evaluated.

## Send to Unreal Integration

The Send to Unreal process with do most of the major things like importing the Mesh with all the shape keys and linking Control Rig and the BPs and .dna file. Also it will import and link the 3 color/normal wrinkle map textures on the head material instance.

The Texture Logic Node Input Names are 1-to-1 with Unreal Material Instance Parameter names. Any image node you plug into one of these inputs in blender will be exported and linked onto the material instance in unreal.

* `Color_MAIN`
* `Color_CM1`
* `Color_CM2`
* `Color_CM3`
* `Normal_MAIN`
* `Normal_WM1`
* `Normal_WM2`
* `Normal_WM3`
* `Cavity_MAIN`
* `Roughness_MAIN`

![](../images/textures/4.png){: class="rounded-image center-image" style="height:400px"}
![](../images/textures/5.png){: class="rounded-image center-image" style="height:400px"}