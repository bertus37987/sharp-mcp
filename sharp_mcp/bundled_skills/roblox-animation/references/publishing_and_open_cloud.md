# Publishing Animations & Open Cloud Upload Rules

## 1. Choosing Between Local Preview vs. Cloud Publishing

| Path | Speed | Output ID | Editable in Studio? | Works in Published Live Servers? |
| :--- | :--- | :--- | :--- | :--- |
| **`AnimationClipProvider:RegisterAnimationClip()`** | Instant (0s) | Temporary session ID | Yes (copy under `ServerStorage.RBX_ANIMSAVES`) | **No** (Studio session only) |
| **Studio Animation Editor -> Publish to Roblox** | Manual click | Permanent `rbxassetid://` | Yes | **Yes** |
| **Studio 3D Importer / `Import from FBX Animation...`** | Seconds | Local clip -> Publish | Yes | After Publish -> **Yes** |
| **Open Cloud `POST /assets/v1/assets` (`.rbxmx`)** | Automated API | Permanent `rbxassetid://` | Re-upload to update | **Yes** |

---

## 2. Critical Open Cloud Format Rule (`assetType = "Animation"`)

Verified against `https://create.roblox.com/docs/en-us/cloud/guides/usage-assets`:
- **`assetType: "Animation"` ONLY accepts `.rbxm` or `.rbxmx` (`contentType: "model/x-rbxm"`)!**
- **Do NOT upload `.fbx` or `.glb` with `assetType: "Animation"`** — Open Cloud only accepts `.fbx`/`.obj` for `assetType: "Model"`.
- Always confirm with the user before triggering an Open Cloud upload (it publishes assets to the user's or group's Roblox Creator inventory).

---

## 3. Minimal Valid `.rbxmx` XML Structure for `KeyframeSequence`

`blender_bake_to_roblox.py` generates this XML directly:
```xml
<?xml version="1.0" encoding="utf-8"?>
<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">
  <Item class="KeyframeSequence" referent="RBX1">
    <Properties>
      <string name="Name">MyClip</string>
      <bool name="Loop">true</bool>
      <token name="Priority">1</token> <!-- Idle=0, Movement=1, Action=2, Action2=3, Action3=4, Action4=5, Core=1000 -->
    </Properties>
    <Item class="Keyframe" referent="RBX2">
      <Properties>
        <string name="Name">KF_0</string>
        <float name="Time">0</float>
      </Properties>
      <!-- Optional KeyframeMarker direct child of Keyframe -->
      <Item class="KeyframeMarker" referent="RBX3">
        <Properties>
          <string name="Name">Footstep</string>
          <string name="Value">Left</string>
        </Properties>
      </Item>
      <!-- Nested Pose hierarchy starting at HumanoidRootPart (or PrimaryPart) -->
      <Item class="Pose" referent="RBX4">
        <Properties>
          <string name="Name">HumanoidRootPart</string>
          <CoordinateFrame name="CFrame">...</CoordinateFrame>
          <float name="Weight">1</float>
          <token name="EasingStyle">5</token> <!-- CubicV2=5, Linear=0, Constant=1 -->
          <token name="EasingDirection">2</token> <!-- In=0, Out=1, InOut=2 -->
        </Properties>
        <Item class="Pose" referent="RBX5"> ... </Item>
      </Item>
    </Item>
  </Item>
</roblox>
```
*(Wait: verify `Priority` token integers in Studio! Historically Roblox's `Enum.AnimationPriority` had `Core=1000` in XML? WAIT — let's verify the EXACT `Enum.AnimationPriority.*.Value` integers inside live Roblox Studio during verification!)*

---

## 4. Uploading via Roblox Studio MCP (`open_cloud_invoke`)

Before calling `open_cloud_invoke`, invoke Roblox's built-in `rbx-permissions` and `rbx-open-cloud-usage` skills in Studio MCP!
1. Ensure the `.rbxmx` file is inside a directory approved in **Studio Assistant Settings -> MCP Permissions**.
2. Call `open_cloud_invoke`:
   - `method`: `"POST"`
   - `endpoint`: `"/assets/v1/assets"`
   - `scopes`: `["asset:read", "asset:write"]`
   - `body`: JSON string containing `"request"` (`assetType: "Animation"`, `displayName`, `description`, `creationContext.creator.userId` or `groupId`)
   - `files`: `[{ "name": "fileContent", "path": "C:/.../MyClip.rbxmx", "contentType": "model/x-rbxm" }]`
3. Poll `GET /assets/v1/operations/{operationId}` until `done == true` and extract `response.assetId` -> `"rbxassetid://" .. assetId`.
