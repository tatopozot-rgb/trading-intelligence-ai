from copy import deepcopy
from decimal import localcontext
import unittest

from execution_context import ContextoInvalido, hash_contenido
from execution_filters import FiltroInvalido
from execution_percent import validar_porcentaje_offline


class PercentTests(unittest.TestCase):
    def setUp(self):
        self.orden=dict(symbol='FIXTUREUSDT',side='BUY',type='LIMIT',timeInForce='GTC',price='100',quantity='1')
        self.filtro=dict(filterType='PERCENT_PRICE_BY_SIDE',avgPriceMins=5,
                         bidMultiplierDown='0.5',bidMultiplierUp='1.2',askMultiplierDown='0.8',askMultiplierUp='2')
        self.evidencia=dict(schema='PRECIO_PORCENTUAL_FIXTURE_V1',entorno='TESTNET_FIXTURE',simbolo='FIXTUREUSDT',
                           referencia=dict(estado='PRESENTE',precio='100',observado_ms=1000,recibido_ms=1100))

    def validar(self, **opciones):
        return validar_porcentaje_offline(self.orden,self.filtro,self.evidencia,**{
            'simbolo_filtro':'FIXTUREUSDT','evidencia_hash_esperado':hash_contenido(self.evidencia),
            'filtro_hash_esperado':hash_contenido(self.filtro),
            'ahora_ms':1200,'max_edad_ms':200,**opciones})

    def ausente(self, minutos=5):
        self.filtro['avgPriceMins']=minutos
        self.evidencia['referencia']=dict(estado='AUSENTE',observado_ms=1000,recibido_ms=1100)
        self.evidencia['sustituto']=dict(tipo='VWAP' if minutos else 'ULTIMO_TRADE',precio='100',
                                       avg_price_mins=minutos,observado_ms=1000,recibido_ms=1100)

    def test_presente_limites_buy_inclusivos_no_muta(self):
        antes=deepcopy((self.orden,self.filtro,self.evidencia))
        r=self.validar()
        self.assertEqual(r['fuente'],'REFERENCE_PRICE')
        self.assertFalse(r['enviable']); self.assertFalse(r['autorizado'])
        self.assertEqual((self.orden,self.filtro,self.evidencia),antes)
        for p in ('50','120'):
            self.orden['price']=p; self.validar()
        for p in ('49.999','120.001'):
            self.orden['price']=p
            with self.assertRaises(FiltroInvalido): self.validar()

    def test_limites_sell_no_usa_bid(self):
        self.orden['side']='SELL'
        for p in ('80','200'):
            self.orden['price']=p; self.validar()
        for p in ('79.999','200.001'):
            self.orden['price']=p
            with self.assertRaises(FiltroInvalido): self.validar()

    def test_percent_price_no_depende_del_lado(self):
        self.filtro=dict(filterType='PERCENT_PRICE',avgPriceMins=5,multiplierDown='0.7',multiplierUp='1.3')
        for lado in ('BUY','SELL'):
            self.orden['side']=lado
            for p in ('70','130'):
                self.orden['price']=p; self.validar()
            self.orden['price']='130.001'
            with self.assertRaises(FiltroInvalido): self.validar()

    def test_ausencia_explicita_vwap_ventana_exacta(self):
        self.ausente()
        self.assertEqual(self.validar()['fuente'],'VWAP')
        self.evidencia['sustituto']['avg_price_mins']=1
        with self.assertRaises(ContextoInvalido): self.validar()

    def test_ultimo_trade_solo_ventana_cero(self):
        self.ausente(0)
        self.assertEqual(self.validar()['fuente'],'ULTIMO_TRADE')
        self.evidencia['sustituto']['tipo']='VWAP'
        with self.assertRaises(ContextoInvalido): self.validar()

    def test_no_fallback_con_referencia_presente_o_desconocida(self):
        self.ausente()
        self.evidencia['referencia']['estado']='DESCONOCIDO'
        with self.assertRaises(ContextoInvalido): self.validar()
        self.evidencia['referencia'].update(estado='PRESENTE',precio='150')
        with self.assertRaises(ContextoInvalido): self.validar()
        del self.evidencia['sustituto']
        r=self.validar()
        self.assertEqual(r['minimo'],'75.0')
        self.assertEqual(r['maximo'],'180.0')

    def test_fuentes_aproximadas_rechazadas(self):
        self.ausente()
        for fuente in ('TICKER_24H','VELA','SMA','ULTIMO_TRADE','REFERENCE_PRICE'):
            self.evidencia['sustituto']['tipo']=fuente
            with self.subTest(fuente=fuente),self.assertRaises(ContextoInvalido): self.validar()

    def test_caducidad_fronteras_no_se_refresca_con_recepcion(self):
        self.validar()
        with self.assertRaises(ContextoInvalido): self.validar(ahora_ms=1201)
        self.evidencia['referencia']['recibido_ms']=1201
        with self.assertRaises(ContextoInvalido): self.validar(ahora_ms=1201)
        self.evidencia['referencia'].update(observado_ms=1250,recibido_ms=1250)
        with self.assertRaises(ContextoInvalido): self.validar()
        self.evidencia['referencia'].update(observado_ms=1100,recibido_ms=1000)
        with self.assertRaises(ContextoInvalido): self.validar()

    def test_ausencia_y_sustituto_necesitan_frescura(self):
        self.ausente()
        self.evidencia['referencia']['observado_ms']=999
        with self.assertRaises(ContextoInvalido): self.validar()
        self.evidencia['referencia']['observado_ms']=1000
        self.evidencia['sustituto']['observado_ms']=999
        with self.assertRaises(ContextoInvalido): self.validar()

    def test_contexto_ausente_hash_y_simbolos(self):
        with self.assertRaises(ContextoInvalido): self.validar(simbolo_filtro='OTRO')
        fijado=hash_contenido(self.evidencia)
        self.evidencia['referencia']['precio']='101'
        with self.assertRaises(ContextoInvalido): self.validar(evidencia_hash_esperado=fijado)
        self.evidencia['simbolo']='OTRO'
        with self.assertRaises(ContextoInvalido): self.validar()
        self.evidencia={}
        with self.assertRaises(ContextoInvalido): self.validar()

    def test_rangos_y_formatos_filtros_no_coercion(self):
        original=deepcopy(self.filtro)
        for cambios in ({'avgPriceMins':True},{'avgPriceMins':-1},{'bidMultiplierUp':'0'},
                        {'askMultiplierDown':'3'},{'bidMultiplierDown':0.5},{'extra':1}, {'filterType':'FUTURO'}):
            self.filtro={**original,**cambios}
            with self.subTest(cambios=cambios),self.assertRaises(ValueError): self.validar()

    def test_precios_referencia_invalidos_y_entornos(self):
        for valor in ('0','NaN','Infinity','1e2',100,True):
            self.evidencia['referencia']['precio']=valor
            with self.subTest(valor=valor),self.assertRaises(ValueError): self.validar()
        self.evidencia['referencia']['precio']='100'
        self.evidencia['entorno']='BINANCE_PUBLIC_MARKET_DATA'
        with self.assertRaises(ContextoInvalido): self.validar()

    def test_precision_independiente_del_contexto_global(self):
        self.evidencia['referencia']['precio']='100.00000000000000000000000000000000000001'
        with localcontext() as ctx:
            ctx.prec=6
            r=self.validar()
        self.assertEqual(r['maximo'],'120.000000000000000000000000000000000000012')

    def test_ordenes_no_simples_y_tiempos_invalidos(self):
        for tiempo in (True,-1,'1200',1200.0,2**63):
            with self.subTest(tiempo=tiempo),self.assertRaises(ValueError): self.validar(ahora_ms=tiempo)
        self.orden['icebergQty']='0.1'
        with self.assertRaises(FiltroInvalido): self.validar()

    def test_observaciones_distintas_no_componen_ausencia(self):
        self.ausente()
        self.evidencia['sustituto']['observado_ms']=1001
        with self.assertRaises(ContextoInvalido): self.validar()
        self.evidencia['sustituto']['observado_ms']=1000
        self.validar()

    def test_filtro_fijado_no_se_sustituye(self):
        fijado=hash_contenido(self.filtro)
        self.filtro['avgPriceMins']=1
        with self.assertRaises(ContextoInvalido): self.validar(filtro_hash_esperado=fijado)
        self.filtro['avgPriceMins']=5
        self.filtro['bidMultiplierUp']='1.3'
        with self.assertRaises(ContextoInvalido): self.validar(filtro_hash_esperado=fijado)


if __name__ == '__main__':
    unittest.main()
