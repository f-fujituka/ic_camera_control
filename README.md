# IC Camera Control
The Imaging Source社製USBカメラ用のCameraControl。  
参考:  https://github.com/TheImagingSource/IC-Imaging-Control-Samples/tree/master/Python/tisgrabber

# 必要条件
opencv-python

# インストール方法
```
pip install git+https://github.com/f-fujituka/ic_camera_control.git 
```

# クイックスタート
```python
import logging

import cv2

from ic_camera_control.ic_camera_control import IcCameraControl


cap = IcCameraControl(config_file_path="camera_config.xml")

while True:
    _, frame = cap.read()

    cv2.imshow("cam", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
```

# LICENSE
Copyright (C) 2024, サイトー株式会社, all rights reserved.

# INCLUDED
https://github.com/TheImagingSource/IC-Imaging-Control-Samples/tree/master/Python/tisgrabber/samples  
tisgrabber.py  
tisgrabber_x64.dll  
TIS_UDSHL11_x64.dll  
