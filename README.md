# M.I.L.O. - Motor Inteligente de Lógica Operativa

Esta es la aplicación web construida en Python y Streamlit que implementa el **Protocolo D v3.9.5** para la generación determinista de señales de trading y el módulo de mejora continua (CCI).

## Estructura del Proyecto

*   `app.py`: Archivo principal de la aplicación Streamlit. Contiene la interfaz de usuario, la lógica de las pestañas y la integración con el protocolo.
*   `milo_protocol.py`: Contiene la clase `MiloProtocol` con la implementación de los 10 pasos del Protocolo D v3.9.5 (cálculo de zonas, veto, riesgo, etc.).
*   `requirements.txt`: Lista de dependencias de Python necesarias para ejecutar la aplicación (Streamlit, pandas, etc.).
*   `cci_operations.json`: (Generado automáticamente) Base de datos JSON que almacena el registro de operaciones cerradas para el análisis estadístico del CCI.

## Instrucciones de Despliegue Permanente (Streamlit Cloud)

Para desplegar esta aplicación de forma permanente y gratuita, siga estos pasos:

1.  **Crear un Repositorio en GitHub:**
    *   Cree un nuevo repositorio en su cuenta de GitHub (ej. `milo-trading-app`).
2.  **Subir los Archivos:**
    *   Suba los siguientes archivos a la raíz de su nuevo repositorio:
        *   `app.py`
        *   `milo_protocol.py`
        *   `requirements.txt`
        *   `README.md`
        *   `.gitignore` (para evitar subir archivos innecesarios)
3.  **Desplegar en Streamlit Cloud:**
    *   Vaya a [Streamlit Cloud](https://share.streamlit.io/).
    *   Haga clic en **"New app"** (Nueva aplicación).
    *   Conecte su cuenta de GitHub.
    *   Seleccione el repositorio que acaba de crear (`milo-trading-app`).
    *   Asegúrese de que la rama principal sea la correcta (generalmente `main` o `master`).
    *   Asegúrese de que el archivo principal sea `app.py`.
    *   Haga clic en **"Deploy!"** (¡Desplegar!).

Streamlit Cloud se encargará de instalar las dependencias y ejecutar la aplicación, proporcionándole un enlace permanente.

**¡En memoria de Milo!**
**Arquitecto/Ingeniero del Sistema:** BY ANIBAL GABRIEL MELLADO LAGOS
