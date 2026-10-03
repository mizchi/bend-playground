"""Use the standalone GPUI package with the playground's shared build cache."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "packages/bend-gpui"
TARGET = ROOT / "build/gpui/target"
spec = importlib.util.spec_from_file_location("bend_gpui_package", LIBRARY / "build.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
DEPLOYMENT = package.DEPLOYMENT
instrument_metal = package.instrument_metal


def cargo(*args):
    return package.cargo(*args, target_dir=TARGET)


def compile_app(*args, **kwargs):
    return package.compile_app(*args, target_dir=TARGET, **kwargs)
