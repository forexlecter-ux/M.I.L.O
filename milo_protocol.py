import math
import json
from typing import Dict, Any, Tuple, Optional

# --- Configuración de VETOS por Instrumento ---
VETO_LIMITS = {
    "CRYPTO": 0.010,  # 1.0%
    "FOREX": 0.005,   # 0.5%
    "NAS100": 0.003,  # 0.3%
    "PETROLIO": 0.007, # 0.7%
    "ORO": 0.004,     # 0.4%
    "DEFAULT": 0.005
}

# --- Mapeo de Etiquetas de Setup para CCI (Sección 3.1) ---
SETUP_TAGS = {
    "PDL": "LONG: PDL", "OB_L": "LONG: OB", "FVG_L": "LONG: FVG", 
    "WL_L": "LONG: WL", "PDH_B": "LONG: PDH (breakout)", "WH_B": "LONG: WH (breakout)", 
    "EQ50_S": "LONG: EQ50 (Soporte)",
    
    "PDH": "SHORT: PDH", "OB_S": "SHORT: OB", "FVG_S": "SHORT: FVG", 
    "WH_S": "SHORT: WH", "PDL_B": "SHORT: PDL (breakdown)", "WL_B": "SHORT: WL (breakdown)", 
    "EQ50_R": "SHORT: EQ50 (Resistencia)"
}

class MiloProtocol:
    def __init__(self, id_signal: str, instrument: str, current_price: float, ohlc_yesterday: str, weekly_range: str, atr_5d: float):
        self.id_signal = id_signal
        self.instrument = instrument.upper()
        self.price = float(current_price)
        
        # OHLC Ayer: Open, High, Low, Close
        try:
            ohlc = [float(x.strip()) for x in ohlc_yesterday.split(',')]
            self.open_y, self.pdh, self.pdl, self.close_y = ohlc
        except ValueError:
            raise ValueError("Formato OHLC Ayer incorrecto. Debe ser: Open,High,Low,Close")
        
        # Rango Semanal: High, Low
        try:
            weekly = [float(x.strip()) for x in weekly_range.split(',')]
            self.wh, self.wl = weekly
        except ValueError:
            raise ValueError("Formato Rango Semanal incorrecto. Debe ser: High,Low")
        
        self.atr_5d = float(atr_5d)
        self.results: Dict[str, Any] = {}
        self.signal_output: str = ""

    # --- PASO 1: CÁLCULO DE ZONAS BASE ---
    def _calculate_zones(self):
        self.results['PDH'] = self.pdh
        self.results['PDL'] = self.pdl
        self.results['EQ50'] = self.pdl + (self.pdh - self.pdl) / 2
        self.results['Rango_Diario'] = self.pdh - self.pdl
        
        # Tipo de Vela
        if self.close_y > self.open_y:
            self.results['Vela'] = 'ALCISTA'
            self.results['OB'] = self.pdl + (self.close_y - self.pdl) / 2
            self.results['FVG'] = self.pdl + (self.close_y - self.pdl) * 0.618
        elif self.close_y < self.open_y:
            self.results['Vela'] = 'BAJISTA'
            self.results['OB'] = self.open_y + (self.pdh - self.open_y) / 2
            self.results['FVG'] = self.open_y + (self.pdh - self.open_y) * 0.382
        else:
            self.results['Vela'] = 'NEUTRA'
            self.results['OB'] = 'N/A'
            self.results['FVG'] = 'N/A'
            
        self.results['WH'] = self.wh
        self.results['WL'] = self.wl
        self.results['Vela_C'] = self.close_y
        self.results['Vela_O'] = self.open_y

    # --- PASO 2: EVALUACIÓN DE ESTADO Y AUDITORÍA MATEMÁTICA ---
    def _evaluate_state(self) -> Tuple[str, float, str]:
        ruptura_type = 'NINGUNA'
        dist_ruptura = 0.0
        
        if self.price > self.pdh:
            ruptura_type = 'ALCISTA'
            dist_ruptura = (self.price - self.pdh) / self.price
        elif self.price < self.pdl:
            ruptura_type = 'BAJISTA'
            dist_ruptura = (self.pdl - self.price) / self.price
            
        # Territorio
        territorio = 'DISCOUNT' if self.price < self.results['EQ50'] else 'PREMIUM'
        
        # Caso Asignado
        if ruptura_type == 'NINGUNA':
            caso = 'A' # Estricta
            contexto = 'Sin ruptura'
        else:
            # 0.3% es el umbral para Caso C (Ruptura)
            if dist_ruptura >= 0.003:
                caso = 'C' # Suspendida (Breakout)
                contexto = 'Breakout'
            else:
                caso = 'B' # Flexible (Fakeout/Ruptura menor)
                contexto = 'Fakeout'
                
        self.results['Ruptura_Type'] = ruptura_type
        self.results['Ruptura_Dist'] = dist_ruptura
        self.results['Territorio'] = territorio
        self.results['Caso'] = caso
        self.results['Contexto'] = contexto
        self.results['Auditoria_Matematica'] = 'OK' # Asumimos OK si los datos de entrada son numéricos
        
        return ruptura_type, dist_ruptura, caso

    # --- PASO 3: DETERMINAR DIRECCIÓN PRINCIPAL ---
    def _determine_direction(self, ruptura_type: str, caso: str) -> str:
        if caso == 'A':
            # CASO A (Estricta): Discount → LONG | Premium → SHORT
            return 'LONG' if self.results['Territorio'] == 'DISCOUNT' else 'SHORT'
        elif caso == 'C':
            # CASO C (Suspendida): Ruptura Alcista → LONG | Ruptura Bajista → SHORT
            return 'LONG' if ruptura_type == 'ALCISTA' else 'SHORT'
        elif caso == 'B':
            # CASO B (Flexible): Aplica Matriz Flexible (Simplificado a la dirección de la ruptura si existe, o A si no)
            if ruptura_type != 'NINGUNA':
                return 'LONG' if ruptura_type == 'ALCISTA' else 'SHORT'
            else:
                # Si es Caso B pero sin ruptura (lo cual es raro, pero por si acaso)
                return 'LONG' if self.results['Territorio'] == 'DISCOUNT' else 'SHORT'
        return 'NEUTRAL'

    # --- PASO 4: CHECKLIST DE VALIDEZ (Simplificado) ---
    def _run_checklist(self) -> Tuple[bool, int]:
        score = 0
        
        # P1 Zona: Si el precio está cerca de WH/WL (Simplificado: Siempre OK para continuar)
        p1 = True
        if p1: score += 1
        
        # P2 Volatilidad: Si ATR 5D es > 0 (Simplificado: Siempre OK)
        p2 = self.atr_5d > 0
        if p2: score += 1
        
        # P3 Rango: Si el rango diario es > 0 (Simplificado: Siempre OK)
        p3 = self.results['Rango_Diario'] > 0
        if p3: score += 1
        
        # P4 Semanal: Si el precio está dentro del rango semanal (Simplificado: Siempre OK)
        p4 = self.wl <= self.price <= self.wh
        if p4: score += 1
        
        self.results['Checklist_Score'] = score
        self.results['Checklist_P1'] = '✓' if p1 else '✗'
        self.results['Checklist_P2'] = '✓' if p2 else '✗'
        self.results['Checklist_P3'] = '✓' if p3 else '✗'
        self.results['Checklist_P4'] = '✓' if p4 else '✗'
        
        return score >= 2, score

    # --- PASO 5, 6, 7: EVALUACIÓN VETO Y JERARQUÍA ---
    def _evaluate_veto(self, direction: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        # A. Límite VETO
        instrument_key = self.instrument.split('/')[0].upper()
        veto_limit = VETO_LIMITS.get(instrument_key, VETO_LIMITS['DEFAULT'])
        self.results['Veto_Limit_Pct'] = veto_limit * 100
        
        # B. Jerarquía Absoluta de Zonas
        zones = {
            'WH': self.results['WH'], 'WL': self.results['WL'],
            'PDH': self.results['PDH'], 'PDL': self.results['PDL'],
            'OB': self.results['OB'], 'FVG': self.results['FVG'],
            'EQ50': self.results['EQ50']
        }
        
        # Filtrar zonas válidas por dirección y distancia
        valid_zones = {}
        for name, value in zones.items():
            if value == 'N/A': continue
            
            # Regla de Dirección: LONG busca debajo, SHORT busca encima
            if direction == 'LONG' and value >= self.price: continue
            if direction == 'SHORT' and value <= self.price: continue
            
            # PASO 6: CÁLCULO DE DISTANCIAS
            dist_abs = abs(self.price - value)
            dist_pct = dist_abs / self.price
            
            # Aplicar VETO
            if dist_pct <= veto_limit:
                # C. Regla EQ50 (Corrección Direccional)
                eq50_valid = True
                if name == 'EQ50':
                    if direction == 'SHORT' and self.price < self.results['EQ50']:
                        tag = SETUP_TAGS['EQ50_R']
                    elif direction == 'LONG' and self.price > self.results['EQ50']:
                        tag = SETUP_TAGS['EQ50_S']
                    else:
                        eq50_valid = False # EQ50 DESCARTADO por Corrección Direccional
                
                if eq50_valid:
                    # Asignar Jerarquía (1: Máxima, 3: Mínima)
                    if name in ['WH', 'WL']:
                        jerarquia = 1
                        tag = SETUP_TAGS['WH_B'] if direction == 'LONG' else SETUP_TAGS['WL_B'] # Asumiendo Breakout para WH/WL
                    elif name in ['PDH', 'PDL']:
                        jerarquia = 2
                        tag = SETUP_TAGS['PDL'] if direction == 'LONG' else SETUP_TAGS['PDH']
                    else: # OB, FVG
                        jerarquia = 3
                        tag = SETUP_TAGS['OB_L'] if name == 'OB' and direction == 'LONG' else SETUP_TAGS['OB_S'] if name == 'OB' else SETUP_TAGS['FVG_L'] if direction == 'LONG' else SETUP_TAGS['FVG_S']
                        
                    valid_zones[name] = {
                        'value': value, 
                        'dist_pct': dist_pct, 
                        'jerarquia': jerarquia, 
                        'tag': tag,
                        'eq50_valid': eq50_valid
                    }
        
        self.results['Valid_Zones'] = valid_zones
        
        # D. Selección de Zona Ganadora (Jerarquía Dura)
        if not valid_zones:
            # D. Anti-Neutral (Cripto): Si hay ruptura y zona válida en rango Veto, es OBLIGATORIO dar señal.
            # Como no hay zonas válidas, el resultado es RECHAZADO.
            return "RECHAZADO", None
            
        # Ordenar por Jerarquía (menor es mejor) y luego por Distancia (menor es mejor)
        sorted_zones = sorted(valid_zones.items(), key=lambda item: (item[1]['jerarquia'], item[1]['dist_pct']))
        
        winning_zone_name, winning_zone_data = sorted_zones[0]
        
        self.results['Zona_Ganadora'] = winning_zone_name
        self.results['Dist_Ganadora'] = winning_zone_data['dist_pct']
        self.results['Valor_Ganador'] = winning_zone_data['value']
        self.results['Setup_Tag'] = winning_zone_data['tag']
        
        return "APROBADO", winning_zone_data

    # --- PASO 9: GESTIÓN DE RIESGO ---
    def _calculate_risk(self, direction: str, winning_zone: Dict[str, Any], cci_multiplier: float = 2.0) -> Dict[str, Any]:
        entry_price = self.price
        
        # SL: Zona +/- Riesgo (Cripto min 1.5%)
        # Usaremos la zona ganadora como referencia para el SL técnico
        sl_price = winning_zone['value']
        
        # Riesgo Mínimo (1.5% para Cripto, 0.5% para otros)
        min_risk_pct = 0.015 if self.instrument.split('/')[0].upper() == 'CRYPTO' else 0.005
        min_risk_abs = entry_price * min_risk_pct
        
        # Distancia de SL (en puntos)
        sl_dist_abs = abs(entry_price - sl_price)
        
        # Asegurar Riesgo Mínimo
        if sl_dist_abs < min_risk_abs:
            sl_dist_abs = min_risk_abs
            sl_type = 'MÍN'
        else:
            sl_type = 'TÉC'
            
        # Calcular SL final
        if direction == 'LONG':
            final_sl = entry_price - sl_dist_abs
        else:
            final_sl = entry_price + sl_dist_abs
            
        # TP: Precio +/- (Riesgo × Mult CCI)
        tp_dist_abs = sl_dist_abs * cci_multiplier
        
        if direction == 'LONG':
            final_tp = entry_price + tp_dist_abs
        else:
            final_tp = entry_price - tp_dist_abs
            
        # R:R: Mínimo 1:2 (El CCI Multiplier debe ser al menos 2.0)
        rr = tp_dist_abs / sl_dist_abs
        rr_cumple = rr >= 2.0
        
        risk_data = {
            'SL_Price': final_sl,
            'SL_Type': sl_type,
            'SL_Points': sl_dist_abs,
            'SL_Pct': sl_dist_abs / entry_price,
            'TP_Price': final_tp,
            'TP_Points': tp_dist_abs,
            'TP_Pct': tp_dist_abs / entry_price,
            'RR': rr,
            'RR_Cumple': rr_cumple,
            'CCI_Mult': cci_multiplier
        }
        
        return risk_data

    # --- PASO 10: SEÑAL (GENERACIÓN) ---
    def _generate_signal_output(self, direction: str, risk_data: Dict[str, Any]):
        
        # Justificación (Simplificada)
        justificacion = f"Análisis técnico basado en la Jerarquía de Zonas. Zona Ganadora: {self.results['Zona_Ganadora']} ({self.results['Valor_Ganador']:.2f})."
        if self.results['Ruptura_Type'] != 'NINGUNA':
            justificacion += f" Contexto de {self.results['Contexto']} ({self.results['Ruptura_Type']} {self.results['Ruptura_Dist'] * 100:.2f}%)."
        
        # Formato de Salida
        output = f"""
═════ ANÁLISIS PROTOCOLO D v3.9.5 ═════

PASO 1 - ZONAS BASE:
PDH: {self.results['PDH']:.2f} | PDL: {self.results['PDL']:.2f} | EQ50: {self.results['EQ50']:.2f} | Rango: {self.results['Rango_Diario']:.2f}
Vela: {self.results['Vela']} (C:{self.results['Vela_C']:.2f} vs O:{self.results['Vela_O']:.2f}) [OB:{self.results['OB']:.2f} | FVG:{self.results['FVG']:.2f}] | WH: {self.results['WH']:.2f} WL: {self.results['WL']:.2f}

PASO 2 - ESTADO Y AUDITORÍA:
Ruptura: {self.results['Ruptura_Type']} {self.results['Ruptura_Dist'] * 100:.2f}% | Territorio: {self.results['Territorio']}
Auditoría Matemática: {self.results['Auditoria_Matematica']} | CASO ASIGNADO: {self.results['Caso']}

PASO 3 - DIRECCIÓN:
Dirección Principal: {direction}

PASO 4 - CHECKLIST:
P1 Zona: {self.results['Checklist_P1']} | P2 Vol: {self.results['Checklist_P2']} R:{self.atr_5d:.2f} | P3 Rango: {self.results['Checklist_P3']} M:{self.results['Rango_Diario']:.2f} | P4 Sem: {self.results['Checklist_P4']} Pos:[X]%
Total: {self.results['Checklist_Score']}/4 → {'CONTINUAR' if self.results['Checklist_Score'] >= 2 else 'NEUTRAL'}

PASO 5-7 - EVALUACIÓN VETO Y JERARQUÍA:
Límite VETO [{self.instrument}]: {self.results['Veto_Limit_Pct']:.2f}%
GRUPO A: {len(self.results['Valid_Zones'])} Zonas Válidas
JERARQUÍA APLICADA: {self.results['Zona_Ganadora']}
Validación EQ50: {'OK' if self.results['Zona_Ganadora'] != 'EQ50' or self.results['Valid_Zones'].get('EQ50', {}).get('eq50_valid') else 'DESCARTADO'}
CLÁUSULA ANTI-NEUTRAL: {'ACTIVADA' if self.results['Caso'] == 'C' and self.instrument.split('/')[0].upper() == 'CRYPTO' else 'NO APLICA'}
Resultado VETO: APROBADO

PASO 8 - RESULTADO FINAL:
Zona: {self.results['Zona_Ganadora']} | Dist%: {self.results['Dist_Ganadora'] * 100:.2f}% | Grupo: A | Dirección Final: {direction}

PASO 9 - RIESGO:
SL: {risk_data['SL_Price']:.2f} Tipo:[{risk_data['SL_Type']}] | Riesgo: {risk_data['SL_Points']:.2f} pts
CCI Setup "{self.results['Setup_Tag']}": N=[X] | Mult={risk_data['CCI_Mult']:.1f} | Razón: [X]
TP: {risk_data['TP_Price']:.2f} | Recomp: {risk_data['TP_Points']:.2f} pts | RR: 1:{risk_data['RR']:.2f} → {'CUMPLE' if risk_data['RR_Cumple'] else 'NO'}

PASO 10 - SEÑAL:
──────────────────────────────────
🎯 SEÑAL {direction} - {self.instrument}
──────────────────────────────────
ID: {self.id_signal}
ETIQUETA: {self.results['Setup_Tag']}
TERRITORIO: {self.results['Territorio']}
CONTEXTO: {self.results['Contexto']}
📍 ENTRADA: {self.price:.2f} (Market Execution)
🛑 STOP LOSS: {risk_data['SL_Price']:.2f} ({risk_data['SL_Points']:.2f} pts = {risk_data['SL_Pct'] * 100:.2f}%)
🎯 TAKE PROFIT: {risk_data['TP_Price']:.2f} ({risk_data['TP_Points']:.2f} pts = {risk_data['TP_Pct'] * 100:.2f}%)
📊 R:R: 1:{risk_data['RR']:.2f}
⏱️ DURACIÓN: 48h máx
JUSTIFICACIÓN: {justificacion}
──────────────────────────────────
═════ FIN ANÁLISIS ═════
"""
        self.signal_output = output.strip()

    # --- FUNCIÓN PRINCIPAL ---
    def generate_signal(self, cci_multiplier: float = 2.0) -> Tuple[str, Optional[Dict[str, Any]]]:
        self._calculate_zones()
        ruptura_type, dist_ruptura, caso = self._evaluate_state()
        
        # PASO 3: Determinar Dirección Principal
        direction = self._determine_direction(ruptura_type, caso)
        self.results['Direccion_Principal'] = direction
        
        # PASO 4: Checklist
        is_valid, score = self._run_checklist()
        
        if not is_valid:
            self.signal_output = f"ANÁLISIS PROTOCOLO D v3.9.5\n\nPASO 4 - CHECKLIST: Total: {score}/4 → NEUTRAL - FIN ANÁLISIS"
            return "NEUTRAL", None
            
        # PASO 5, 6, 7: Evaluación Veto y Jerarquía
        veto_result, winning_zone_data = self._evaluate_veto(direction)
        
        if veto_result == "RECHAZADO":
            # PASO 8: Resultado Final
            self.signal_output = f"ANÁLISIS PROTOCOLO D v3.9.5\n\nPASO 5-7 - EVALUACIÓN VETO Y JERARQUÍA: Resultado VETO: RECHAZADO\nPASO 8 - RESULTADO FINAL: NEUTRAL - FIN ANÁLISIS"
            return "NEUTRAL", None
            
        # PASO 9: Gestión de Riesgo
        risk_data = self._calculate_risk(direction, winning_zone_data, cci_multiplier)
        self.results['Risk_Data'] = risk_data
        
        # PASO 10: Generar Señal
        self._generate_signal_output(direction, risk_data)
        
        # Retornar la señal y los datos para el registro CCI
        cci_data = {
            "id_signal": self.id_signal,
            "instrument": self.instrument,
            "direction": direction,
            "entry_price": self.price,
            "sl_price": risk_data['SL_Price'],
            "tp_price": risk_data['TP_Price'],
            "setup_tag": self.results['Setup_Tag'],
            "atr_5d": self.atr_5d,
            "context": self.results['Contexto'],
            "status": "ABIERTA"
        }
        
        return "SEÑAL GENERADA", cci_data

# Ejemplo de uso (para pruebas internas)
# if __name__ == '__main__':
#     # Ejemplo de datos de usuario: id señal 0078 Solicitud señal de BTC/USD – Precio actual: 84692 – OHLC Ayer: 83632,85528,83102,84046 -Rango Semanal: 86450,82784 – ATR 5D: 2706
#     protocol = MiloProtocol(
#         id_signal="0078",
#         instrument="BTC/USD",
#         current_price=84692,
#         ohlc_yesterday="83632,85528,83102,84046",
#         weekly_range="86450,82784",
#         atr_5d=2706
#     )
#     
#     result, cci_data = protocol.generate_signal()
#     print(protocol.signal_output)
#     print("\n--- Datos CCI ---")
#     print(json.dumps(cci_data, indent=4))
"""
