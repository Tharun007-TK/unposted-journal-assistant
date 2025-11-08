import importlib

def test_app_imports():
    mod = importlib.import_module('app')
    # Verify key symbols exist
    assert hasattr(mod, 'EMO_LABELS')
    assert isinstance(mod.EMO_LABELS, list)
    assert 'Calm' in mod.EMO_LABELS
