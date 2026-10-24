"""Las pruebas históricas verifican el contrato v1 y su conservación tras la migración.
Las pruebas de market_pipeline verifican v2 con la configuración predeterminada.
"""
import pytest
from app.core.config import get_settings

@pytest.fixture(autouse=True)
def legacy_contract_mode(request, monkeypatch):
    if request.module.__name__.split('.')[-1] in {'test_forecasts','test_global_form','test_metrics'}:
        monkeypatch.setattr(get_settings(), 'forecast_architecture', 'legacy-v1')

