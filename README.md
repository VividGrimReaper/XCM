# XCM
an Xbox controller mapper f Blender
# DO NOT RUN THIS CODE, 
# the powershell is def wrong i can tell that just by glancing at it, 
# 100% vibe coded with qwen3-code-next, using git for easy versioning. <----see,  cant   eeven spell gud, DO NOT run my code. 
# Xbox Controller Mapper for Blender 🎮

Turn your Xbox Elite 2 (or any XInput controller) into a full-featured navigation & tool controller—no keyboard required!

✅ Works with **Blender 4.1+**  
✅ Real-time, low-latency polling (~60 Hz)  
✅ Customizable button mappings + fine-tuning sliders  
✅ Built-in documentation in Blender — no browser needed

---

## 🚀 Quick Start

### 1️⃣ Install the Add-on
- In Blender: **Edit → Preferences → Add-ons → Install…**  
- Select `controller_mapper.py`  
- ✅ Enable it (checkbox on right)

### 2️⃣ Install `inputs` Library *(One-time setup)*
Open **PowerShell as Administrator**, then run:
```powershell
cd "C:\Program Files\Blender Foundation\Blender\4.1\python"
.\bin\python.exe -m pip install inputs
