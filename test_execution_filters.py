import copy
from decimal import localcontext
import unittest

from execution_filters import FiltroInvalido, validar_limite_offline


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.orden = dict(symbol='FIXTUREUSDT',side='BUY',type='LIMIT',timeInForce='GTC',price='10.00',quantity='1.000')
        self.simbolo = dict(symbol='FIXTUREUSDT',status='TRADING',isSpotTradingAllowed=True,orderTypes=['LIMIT'],filters=[
            dict(filterType='PRICE_FILTER',minPrice='1',maxPrice='100',tickSize='0.01'),
            dict(filterType='LOT_SIZE',minQty='0.001',maxQty='10',stepSize='0.001'),
            dict(filterType='MIN_NOTIONAL',minNotional='10'),
            dict(filterType='NOTIONAL',minNotional='10',maxNotional='100')])

    def validar(self):
        return validar_limite_offline(self.orden,self.simbolo)

    def test_valida_exacta_sin_mutar_ni_habilitar(self):
        antes = copy.deepcopy((self.orden,self.simbolo))
        resultado = self.validar()
        self.assertFalse(resultado['enviable'])
        self.assertEqual(resultado['notional'],'10.00000')
        self.assertEqual((self.orden,self.simbolo),antes)

    def test_limites_notional_inclusivos(self):
        self.orden['quantity']='10'
        self.validar()
        for precio,cantidad in [('10','0.999'),('10.01','10')]:
            self.orden.update(price=precio,quantity=cantidad)
            with self.assertRaises(FiltroInvalido): self.validar()

    def test_desalineacion_no_se_redondea(self):
        for campo,valor in [('price','10.001'),('quantity','1.0001')]:
            with self.subTest(campo=campo):
                orden = {**self.orden,campo:valor}
                with self.assertRaises(FiltroInvalido): validar_limite_offline(orden,self.simbolo)

    def test_representaciones_invalidas(self):
        for valor in (10.,10,True,'NaN','Infinity','1e1','-10','+10',' 10','0','1'*81):
            with self.subTest(valor=valor),self.assertRaises(FiltroInvalido):
                validar_limite_offline({**self.orden,'price':valor},self.simbolo)

    def test_reglas_precio_cero_desactivadas(self):
        self.simbolo['filters'][0].update(minPrice='0',maxPrice='0',tickSize='0')
        self.orden['price']='10.00001'
        self.validar()

    def test_filtro_desconocido_o_dinamico_no_ignorado(self):
        for tipo in ('PERCENT_PRICE','PERCENT_PRICE_BY_SIDE','MAX_NUM_ORDERS','FUTURO'):
            info = copy.deepcopy(self.simbolo)
            info['filters'].append(dict(filterType=tipo))
            with self.assertRaisesRegex(FiltroInvalido,'no soportado'): validar_limite_offline(self.orden,info)

    def test_ausentes_duplicados_o_malformados(self):
        for filtros in ([],None,self.simbolo['filters'][1:],self.simbolo['filters']+[self.simbolo['filters'][0]],
                        [dict(filterType='LOT_SIZE')]):
            with self.assertRaises(FiltroInvalido): validar_limite_offline(self.orden,{**self.simbolo,'filters':filtros})

    def test_no_asume_tipo_o_permisos(self):
        for cambio in ({'status':'BREAK'},{'symbol':'OTRO'},{'isSpotTradingAllowed':'true'},{'orderTypes':[]}):
            with self.assertRaises(FiltroInvalido): validar_limite_offline(self.orden,{**self.simbolo,**cambio})
        for cambio in ({'type':'MARKET'},{'side':'otro'},{'stopPrice':'9'}):
            with self.assertRaises(FiltroInvalido): validar_limite_offline({**self.orden,**cambio},self.simbolo)

    def test_contexto_decimal_externo_no_cambia_resultado(self):
        esperado = self.validar()
        with localcontext() as contexto:
            contexto.prec=2
            self.assertEqual(self.validar(),esperado)

    def test_cero_step_lote_no_se_inventa(self):
        self.simbolo['filters'][1]['stepSize']='0'
        with self.assertRaises(FiltroInvalido): self.validar()

    def test_multiplo_desde_cero_no_desde_minimo(self):
        self.simbolo['filters'][0].update(minPrice='0.03',tickSize='0.02')
        self.simbolo['filters'][1].update(minQty='0.003',stepSize='0.002')
        self.validar()  # 10 % .02 y 1 % .002, sin restar mínimos.
        self.orden['price']='10.01'
        with self.assertRaises(FiltroInvalido): self.validar()

    def test_notional_maximo_cero_no_se_desactiva(self):
        self.simbolo['filters'][-1].update(minNotional='0',maxNotional='0')
        with self.assertRaises(FiltroInvalido): self.validar()


if __name__=='__main__': unittest.main()
