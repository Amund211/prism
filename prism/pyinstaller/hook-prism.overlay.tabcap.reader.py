from PyInstaller.utils.hooks import collect_data_files

# The model is read from a path next to model.py, not imported
datas = collect_data_files(
    "prism.overlay.tabcap.reader", includes=["rk4_all.onnx", "rk4_all.json"]
)
