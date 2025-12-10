import streamlit as st
import pandas as pd
import json
import os
from milo_protocol import MiloProtocol, VETO_LIMITS, SETUP_TAGS
from typing import Dict, Any, List

# --- Configuración de Archivos ---
CCI_DB_FILE = "/tmp/cci_operations.json"

# --- Funciones de Utilidad para CCI ---

def load_cci_data() -> List[Dict[str, Any]]:
    """Carga los datos del registro CCI desde el archivo JSON."""
    if not os.path.exists(CCI_DB_FILE):
        return []
    with open(CCI_DB_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_cci_data(data: List[Dict[str, Any]]):
    """Guarda los datos del registro CCI en el archivo JSON."""
    with open(CCI_DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def initialize_session_state():
    """Inicializa el estado de sesión de Streamlit."""
    if 'cci_data' not in st.session_state:
        st.session_state.cci_data = load_cci_data()
    if 'open_operations' not in st.session_state:
        st.session_state.open_operations = [op for op in st.session_state.cci_data if op['status'] == 'ABIERTA']

def update_cci_data(new_operation: Dict[str, Any]):
    """Añade una nueva operación al registro y al estado de sesión."""
    st.session_state.cci_data.append(new_operation)
    st.session_state.open_operations.append(new_operation)
    save_cci_data(st.session_state.cci_data)

def close_operation(id_signal: str, result: str, close_price: float = None):
    """Cierra una operación abierta y actualiza las estadísticas."""
    
    # 1. Buscar la operación
    op_index = -1
    for i, op in enumerate(st.session_state.cci_data):
        if op['id_signal'] == id_signal and op['status'] == 'ABIERTA':
            op_index = i
            break
    
    if op_index == -1:
        st.error(f"Operación con ID {id_signal} no encontrada o ya está cerrada.")
        return

    op = st.session_state.cci_data[op_index]
    
    # 2. Calcular P/G y actualizar estado
    op['status'] = result
    op['close_price'] = close_price if close_price is not None else (op['tp_price'] if result == 'TP' else op['sl_price'])
    
    entry = op['entry_price']
    close = op['close_price']
    
    if op['direction'] == 'LONG':
        op['p_g_points'] = close - entry
    else: # SHORT
        op['p_g_points'] = entry - close
        
    # Regla de Blindaje CCI: Si el usuario no proporciona el precio de SL en una orden de cierre, asumir Calidad=0
    if result in ['SL LONG', 'SL SHORT'] and close_price is None:
        op['p_g_points'] = 0 # Calidad=0
        
    # 3. Actualizar el estado de sesión y guardar
    st.session_state.cci_data[op_index] = op
    st.session_state.open_operations = [o for o in st.session_state.open_operations if o['id_signal'] != id_signal]
    save_cci_data(st.session_state.cci_data)
    st.success(f"Operación {id_signal} cerrada como {result}. P/G: {op['p_g_points']:.2f} puntos.")

def get_toxic_setups(cci_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analiza el registro para detectar setups tóxicos."""
    
    closed_ops = [op for op in cci_data if op['status'] in ['TP', 'SL LONG', 'SL SHORT', 'MANUAL']]
    
    # Análisis por Setup Tag
    setup_stats = {}
    for op in closed_ops:
        tag = op['setup_tag']
        if tag not in setup_stats:
            setup_stats[tag] = {'total': 0, 'sl_manual_loss': 0}
        
        setup_stats[tag]['total'] += 1
        if op['status'] in ['SL LONG', 'SL SHORT'] or (op['status'] == 'MANUAL' and op['p_g_points'] < 0):
            setup_stats[tag]['sl_manual_loss'] += 1
            
    toxic_setups = {}
    for tag, stats in setup_stats.items():
        if stats['total'] >= 20: # Mínimo 20 operaciones para evaluar
            loss_rate = stats['sl_manual_loss'] / stats['total']
            if loss_rate > 0.80: # Tasa de pérdida superior al 80%
                toxic_setups[tag] = {'total': stats['total'], 'loss_rate': loss_rate}

    # Análisis por Contexto (ATR 5D > 4500)
    atr_stats = {'total': 0, 'sl_manual_loss': 0}
    for op in closed_ops:
        if op['atr_5d'] > 4500:
            atr_stats['total'] += 1
            if op['status'] in ['SL LONG', 'SL SHORT'] or (op['status'] == 'MANUAL' and op['p_g_points'] < 0):
                atr_stats['sl_manual_loss'] += 1
    
    toxic_context = {}
    if atr_stats['total'] >= 20:
        loss_rate = atr_stats['sl_manual_loss'] / atr_stats['total']
        if loss_rate > 0.80:
            toxic_context['ATR 5D > 4500'] = {'total': atr_stats['total'], 'loss_rate': loss_rate}
            
    return {'setups': toxic_setups, 'context': toxic_context}

# --- Componentes de la UI ---

def ui_generador_milo():
    st.header("Generador de Señales M.I.L.O.")
    
    # Formulario de Entrada
    with st.form("milo_input_form"):
        st.subheader("Datos de Entrada (Única Fuente de Verdad)")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            id_signal = st.text_input("ID Señal", value="0001")
            instrument = st.selectbox("Instrumento", options=list(VETO_LIMITS.keys())[:-1] + ["DEFAULT"], index=0)
        with col2:
            current_price = st.number_input("Precio Actual", min_value=0.0, format="%.4f", value=84692.0)
            ohlc_yesterday = st.text_input("OHLC Ayer (O,H,L,C)", value="83632,85528,83102,84046")
        with col3:
            weekly_range = st.text_input("Rango Semanal (H,L)", value="86450,82784")
            atr_5d = st.number_input("ATR 5D", min_value=0.0, format="%.2f", value=2706.0)
            
        submitted = st.form_submit_button("Generar Señal M.I.L.O.")
        
        if submitted:
            try:
                protocol = MiloProtocol(id_signal, instrument, current_price, ohlc_yesterday, weekly_range, atr_5d)
                result, cci_data = protocol.generate_signal()
                
                st.subheader("Resultado del Análisis")
                
                # Advertencia Estadística (si aplica)
                toxic_setups = get_toxic_setups(st.session_state.cci_data)
                is_toxic = False
                
                if cci_data and cci_data['setup_tag'] in toxic_setups['setups']:
                    st.warning(f"⚠️ ADVERTENCIA ESTADÍSTICA: El setup '{cci_data['setup_tag']}' es tóxico. Tasa de pérdida: {toxic_setups['setups'][cci_data['setup_tag']]['loss_rate'] * 100:.2f}% en {toxic_setups['setups'][cci_data['setup_tag']]['total']} ops.")
                    is_toxic = True
                
                if 'ATR 5D > 4500' in toxic_setups['context'] and atr_5d > 4500:
                    st.warning(f"⚠️ ADVERTENCIA ESTADÍSTICA: El contexto 'ATR 5D > 4500' es tóxico. Tasa de pérdida: {toxic_setups['context']['ATR 5D > 4500']['loss_rate'] * 100:.2f}% en {toxic_setups['context']['ATR 5D > 4500']['total']} ops.")
                    is_toxic = True
                
                # Mostrar Señal
                st.markdown(protocol.signal_output)
                
                # Retroalimentación Visual
                if result == "SEÑAL GENERADA":
                    if cci_data['direction'] == 'LONG':
                        st.markdown("## 🐂 TORO (LONG)")
                    else:
                        st.markdown("## 🐻 OSO (SHORT)")
                        
                    # Registrar la operación
                    update_cci_data(cci_data)
                    st.success(f"Señal {id_signal} registrada como operación abierta.")
                
            except ValueError as e:
                st.error(f"Error de Validación de Datos: {e}")
            except Exception as e:
                st.error(f"Error inesperado durante la generación de la señal: {e}")

    st.markdown("---")
    st.subheader("Cierre de Operaciones Abiertas")
    
    if not st.session_state.open_operations:
        st.info("No hay operaciones abiertas para cerrar.")
        return
        
    df_open = pd.DataFrame(st.session_state.open_operations)
    st.dataframe(df_open[['id_signal', 'instrument', 'direction', 'entry_price', 'sl_price', 'tp_price', 'setup_tag', 'atr_5d']])
    
    # Botones de Cierre
    with st.container():
        col_close1, col_close2, col_close3 = st.columns(3)
        
        # Cierre TP
        with col_close1:
            st.markdown("##### Cierre por TP")
            tp_id = st.selectbox("ID para TP", options=[op['id_signal'] for op in st.session_state.open_operations], key="tp_id_select")
            if st.button(f"Cerrar TP {tp_id}", key="btn_tp"):
                close_operation(tp_id, "TP")
        
        # Cierre SL
        with col_close2:
            st.markdown("##### Cierre por SL")
            sl_id = st.selectbox("ID para SL", options=[op['id_signal'] for op in st.session_state.open_operations], key="sl_id_select")
            op_sl = next((op for op in st.session_state.open_operations if op['id_signal'] == sl_id), None)
            if op_sl:
                sl_type = f"SL {op_sl['direction']}"
                if st.button(f"Cerrar {sl_type} {sl_id}", key="btn_sl"):
                    close_operation(sl_id, sl_type)
        
        # Cierre Manual
        with col_close3:
            st.markdown("##### Cierre Manual")
            manual_id = st.selectbox("ID para Manual", options=[op['id_signal'] for op in st.session_state.open_operations], key="manual_id_select")
            manual_price = st.number_input("Precio de Cierre Manual", min_value=0.0, format="%.4f", key="manual_price_input")
            if st.button(f"Cerrar Manual {manual_id}", key="btn_manual"):
                if manual_price > 0:
                    close_operation(manual_id, "MANUAL", manual_price)
                else:
                    st.error("Debe ingresar un precio de cierre manual válido.")

def ui_registro_cci():
    st.header("Registro CCI y Estadísticas")
    
    cci_data = st.session_state.cci_data
    if not cci_data:
        st.info("El registro CCI está vacío. Genere y cierre algunas operaciones para ver las estadísticas.")
        return
        
    df_cci = pd.DataFrame(cci_data)
    
    st.subheader("Registro Completo de Operaciones")
    st.dataframe(df_cci)
    
    st.subheader("Auditoría de Setups Tóxicos")
    toxic_data = get_toxic_setups(cci_data)
    
    if toxic_data['setups'] or toxic_data['context']:
        st.error("🚨 ¡ATENCIÓN! Setups y Contextos Estadísticamente Tóxicos Detectados (Tasa de Pérdida > 80% en > 20 Ops)")
        
        if toxic_data['setups']:
            st.markdown("##### Setups Tóxicos por Etiqueta")
            df_toxic_setups = pd.DataFrame(toxic_data['setups']).T.reset_index()
            df_toxic_setups.columns = ['Setup Tag', 'Total Ops', 'Tasa de Pérdida']
            df_toxic_setups['Tasa de Pérdida'] = (df_toxic_setups['Tasa de Pérdida'] * 100).map('{:.2f}%'.format)
            st.table(df_toxic_setups)
            
        if toxic_data['context']:
            st.markdown("##### Contextos Tóxicos")
            df_toxic_context = pd.DataFrame(toxic_data['context']).T.reset_index()
            df_toxic_context.columns = ['Contexto', 'Total Ops', 'Tasa de Pérdida']
            df_toxic_context['Tasa de Pérdida'] = (df_toxic_context['Tasa de Pérdida'] * 100).map('{:.2f}%'.format)
            st.table(df_toxic_context)
            
    else:
        st.success("✅ No se han detectado setups o contextos estadísticamente tóxicos (requiere al menos 20 operaciones por criterio).")
        
    st.subheader("Resumen de Rendimiento por Setup")
    
    # Calcular rendimiento por setup
    setup_summary = df_cci.groupby('setup_tag').agg(
        Total_Ops=('id_signal', 'count'),
        Ganadas=('status', lambda x: (x == 'TP').sum()),
        Perdidas=('status', lambda x: (x.str.contains('SL') | (x == 'MANUAL') & (df_cci.loc[x.index, 'p_g_points'] < 0)).sum()),
        Puntos_Netos=('p_g_points', 'sum')
    ).reset_index()
    
    setup_summary['Ratio_Win_Loss'] = setup_summary['Ganadas'] / setup_summary['Perdidas'].replace(0, 1)
    setup_summary = setup_summary.sort_values(by='Ratio_Win_Loss', ascending=False)
    
    st.dataframe(setup_summary)


# --- Función Principal de la Aplicación ---

def main():
    # Inicialización
    initialize_session_state()
    
    st.set_page_config(layout="wide", page_title="M.I.L.O. Trading System")
    st.title("🤖 M.I.L.O. - Motor Inteligente de Lógica Operativa")
    
    # Pestañas
    tab1, tab2 = st.tabs(["Generador M.I.L.O.", "Registro CCI y Estadísticas"])
    
    with tab1:
        ui_generador_milo()
        
    with tab2:
        ui_registro_cci()
        
    # Footer (Sección 4.4)
    st.markdown("---")
    st.markdown("<p style='text-align: center; font-size: small;'><strong>EN MEMORIA DE MILO</strong></p>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: x-small;'>Arquitecto/Ingeniero del Sistema: BY ANIBAL GABRIEL MELLADO LAGOS</p>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
"""
