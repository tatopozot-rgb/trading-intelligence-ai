"""Fixtures de cartera explícitos: no datos históricos, cuenta ni red."""
import copy
from decimal import Decimal, Inexact, ROUND_DOWN, ROUND_UP, localcontext
import random
import unittest

import historical_portfolio as p


def caso(identidad='a', simbolo='BTCUSDT', t=0, fin=None, salida=None, **cambios):
    return dict(id=identidad, simbolo=simbolo, entrada_ms=t, entrada='100', stop='99',
                objetivo='104', salida_ms=fin, salida=salida, comision_pct='0', **cambios)


class PortfolioTests(unittest.TestCase):
    def test_contexto_decimal_externo_no_altera_resultado_ni_huella(self):
        c = caso(fin=1, salida='104')
        c['comision_pct'] = '.1'
        esperado = self.sim([c])
        for redondeo in (ROUND_DOWN, ROUND_UP):
            with localcontext() as contexto:
                contexto.prec = 3
                contexto.rounding = redondeo
                contexto.Emax = 3
                contexto.Emin = -3
                contexto.traps[Inexact] = True
                self.assertEqual(self.sim([c]), esperado)
                self.assertTrue(contexto.traps[Inexact])
                self.assertEqual(contexto.prec, 3)

    def sim(self, casos, **params):
        argumentos = dict(capital_inicial='100', riesgo_operacion_pct='1', perdida_diaria_pct='3',
            max_posiciones=3, inicio_ms=0, fin_ms=86400000*3, politica_empates=p.POLITICA)
        argumentos.update(params)
        return p.simular(casos, **argumentos)

    def test_capital_compartido_no_se_replica_por_candidato(self):
        datos = [caso(), caso('b','ETHUSDT'), caso('c','ADAUSDT')]
        r = self.sim(datos, riesgo_operacion_pct='.5')
        self.assertEqual([d['estado'] for d in r['decisiones']], ['ACEPTADO','ACEPTADO','RECHAZADO'])
        self.assertEqual(r['decisiones'][2]['motivo'], 'SIN_CAPITAL_LIBRE')
        self.assertEqual(Decimal(r['metricas']['capital_comprometido']), 100)
        self.assertEqual(Decimal(r['metricas']['cash_libre']), 0)
        self.assertEqual(r['metricas']['max_posiciones_observadas'], 2)
        self.assertEqual(len(r['abiertas']), 2)

    def test_comision_entrada_reservada_y_salida_una_vez(self):
        c = caso(fin=1, salida='104'); c['comision_pct']='1'
        r = self.sim([c], riesgo_operacion_pct='100', perdida_diaria_pct='100')
        entrada, salida = r['eventos']
        nominal = Decimal(entrada['nominal'])
        self.assertAlmostEqual(float(nominal), 100/1.01)
        self.assertAlmostEqual(float(r['metricas']['saldo_realizado_no_mtm']), (100/1.01)*1.04*.99)
        self.assertAlmostEqual(float(salida['pnl_neto_operacion']), (100/1.01)*1.04*.99-100)
        self.assertAlmostEqual(float(r['metricas']['comisiones']), float(nominal)*.01+float(nominal)*1.04*.01)
        self.assertEqual(r['abiertas'], [])

    def test_censura_no_cierra_ni_inventa_ganancia(self):
        c = caso(); c['comision_pct']='.1'
        r = self.sim([c])
        self.assertEqual([e['tipo'] for e in r['eventos']], ['APERTURA'])
        self.assertEqual(len(r['abiertas']), 1)
        self.assertLess(Decimal(r['metricas']['pnl_realizado_incluye_fees_entrada']), 0)
        self.assertFalse(r['enviable'])

    def test_limite_posiciones_y_simbolo(self):
        r = self.sim([caso(), caso('b'), caso('c','ETHUSDT')], max_posiciones=1, riesgo_operacion_pct='.1')
        self.assertEqual([d['motivo'] for d in r['decisiones']], [None,'SIMBOLO_YA_ABIERTO','MAX_POSICIONES'])

    def test_orden_entrada_json_no_decide_empate(self):
        casos = [caso('z','BTCUSDT'),caso('a','ETHUSDT')]
        r = self.sim(casos, max_posiciones=1)
        self.assertEqual(r, self.sim(list(reversed(casos)), max_posiciones=1))
        self.assertEqual(r['decisiones'][0]['id'], 'a')
        self.assertEqual(r['politica_empates'], p.POLITICA)

    def test_salidas_previas_liberan_capital_a_misma_hora(self):
        r = self.sim([caso(fin=10,salida='100'), caso('b','ETHUSDT',10,20,'100')])
        self.assertEqual(r['metricas']['aceptados'], 2)
        self.assertEqual([e['tipo'] for e in r['eventos']], ['APERTURA','CIERRE','APERTURA','CIERRE'])
        self.assertEqual(Decimal(r['metricas']['saldo_realizado_no_mtm']), 100)

    def test_salida_inmediata_no_se_procesa_antes_de_compra(self):
        r = self.sim([caso(fin=0,salida='100'), caso('b','ETHUSDT')])
        self.assertEqual(r['metricas']['aceptados'], 1)
        self.assertEqual([e['tipo'] for e in r['eventos']], ['APERTURA','CIERRE'])
        self.assertEqual(r['decisiones'][1]['motivo'], 'SIN_CAPITAL_LIBRE')

    def test_perdidas_diarias_no_se_compensan_con_ganancias(self):
        casos = [caso(fin=1,salida='99'),caso('b','ETHUSDT',2,3,'103'),caso('c','ADAUSDT',4)]
        r = self.sim(casos, riesgo_operacion_pct='.5', perdida_diaria_pct='1')
        self.assertEqual(r['decisiones'][-1]['motivo'], 'LIMITE_PERDIDA_DIARIA')
        self.assertEqual(Decimal(r['dias']['0']['perdidas']), Decimal('.5'))
        self.assertGreater(Decimal(r['metricas']['saldo_realizado_no_mtm']), 100)

    def test_base_dia_antes_del_primer_cierre_overnight(self):
        r = self.sim([caso(fin=86400000,salida='102'),caso('b','ETHUSDT',86400001)])
        self.assertEqual(Decimal(r['dias']['1']['saldo_base']), 100)
        self.assertEqual(Decimal(r['decisiones'][1]['saldo_base_dia']), 100)

    def test_riesgo_abierto_se_lleva_al_dia_siguiente(self):
        r = self.sim([caso(),caso('b','ETHUSDT',86400000)], riesgo_operacion_pct='.5', perdida_diaria_pct='.9')
        self.assertEqual(r['decisiones'][1]['motivo'], 'LIMITE_PERDIDA_DIARIA')
        self.assertEqual(r['metricas']['aceptados'], 1)

    def test_gap_puede_exceder_riesgo_y_drawdown_no_es_mtm(self):
        r = self.sim([caso(fin=1,salida='80'),caso('b','ETHUSDT',2)])
        self.assertEqual(Decimal(r['metricas']['drawdown_realizado_usd_no_mtm']), 20)
        self.assertEqual(r['decisiones'][1]['motivo'], 'LIMITE_PERDIDA_DIARIA')

    def test_rechazado_no_genera_pnl_en_su_fecha_de_salida(self):
        r = self.sim([caso(),caso('b','ETHUSDT',1,2,'100000')])
        self.assertEqual(len(r['eventos']),1)
        self.assertEqual(Decimal(r['metricas']['pnl_realizado_incluye_fees_entrada']),0)

    def test_inmutabilidad_candidatos_y_huella_parametros(self):
        casos = [caso()]; original=copy.deepcopy(casos)
        r = self.sim(casos)
        self.assertEqual(casos,original)
        self.assertNotEqual(r['entradas_sha256'], self.sim(casos, capital_inicial='101')['entradas_sha256'])

    def test_validacion_estricta_previa_a_ejecucion(self):
        for campo, v in [('entrada',True),('stop','NaN'),('objetivo','Infinity'),('comision_pct','100'),
                         ('entrada_ms',False),('salida_ms',1),('salida','100'),('id','../a'),('simbolo','XM:EURUSD')]:
            c=caso();c[campo]=v
            with self.subTest(campo=campo,v=v),self.assertRaises(ValueError):self.sim([c])
        with self.assertRaises(ValueError):self.sim([caso(),caso()])
        with self.assertRaises(ValueError):self.sim([caso(fin=86400000*4,salida='100')])
        with self.assertRaises(ValueError):self.sim([caso(t=3,fin=2,salida='100')])
        with self.assertRaises(ValueError):self.sim([caso()],politica_empates=None)
        with self.assertRaises(ValueError):self.sim([caso()],max_posiciones=True)

    def test_lista_vacia_conserva_capital(self):
        r = self.sim([])
        self.assertEqual(Decimal(r['metricas']['cash_libre']),100)
        self.assertEqual(r['eventos'],[])

    def test_conservacion_en_200_escenarios_reproducibles(self):
        azar = random.Random(20260929)
        with localcontext() as ctx:
            ctx.prec = 120
            for indice in range(200):
                candidatos = []
                for n in range(30):
                    t = azar.randrange(0, 100)
                    salida_t = min(200, t+azar.randrange(0, 100))
                    c = caso(str(n), azar.choice(['BTCUSDT','ETHUSDT','ADAUSDT']), t,
                             salida_t, azar.choice(['75','99','101','110']))
                    c['comision_pct'] = azar.choice(['0','.1','1'])
                    if azar.randrange(8)==0:
                        c.update(salida_ms=None,salida=None)
                    candidatos.append(c)
                r = self.sim(candidatos, fin_ms=200, capital_inicial=azar.choice(['1','100','1000000000000']),
                    riesgo_operacion_pct=azar.choice(['.01','1','10']), perdida_diaria_pct=azar.choice(['1','3','100']))
                m=r['metricas']; cash=Decimal(m['cash_libre']); nominal=Decimal(m['capital_comprometido'])
                self.assertGreaterEqual(cash,0)
                self.assertLessEqual(m['max_posiciones_observadas'],3)
                self.assertEqual(m['aceptados']+m['rechazados'],30)
                self.assertLess(abs(cash+nominal-Decimal(m['saldo_realizado_no_mtm'])),Decimal('1e-70'))
                self.assertLess(abs(Decimal(m['capital_inicial'])+Decimal(m['pnl_realizado_incluye_fees_entrada'])
                    -Decimal(m['saldo_realizado_no_mtm'])),Decimal('1e-70'))
                fees=sum((Decimal(e['comision']) for e in r['eventos']), Decimal(0))
                self.assertLess(abs(fees-Decimal(m['comisiones'])),Decimal('1e-70'))
                compras={e['id']:e for e in r['eventos'] if e['tipo']=='APERTURA'}
                for e in r['eventos']:
                    if e['tipo']=='CIERRE':
                        self.assertEqual(e['cantidad'],compras[e['id']]['cantidad'])


if __name__ == '__main__': unittest.main()
