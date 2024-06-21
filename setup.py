from setuptools import setup, find_packages

setup(
    name='ic_camera_control',
    version='0.1.0',
    packages=find_packages(),
    data_files=[("./Lib/site-packages/ic_camera_control", ["./ic_camera_control/TIS_UDSHL11_x64.dll"]),
                ("./Lib/site-packages/ic_camera_control", ["./ic_camera_control/tisgrabber_x64.dll"])],
    include_package_data=True
)