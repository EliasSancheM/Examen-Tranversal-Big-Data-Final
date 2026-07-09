# Evaluación Parcial N° 3 — Procesamiento en línea y panel de control

| Sigla   | Asignatura  | Tiempo Asignado | % Ponderación |
|---------|-------------|-----------------|---------------|
| AVY1101 | Big Data    | 4h              | 35%           |

## 1. Situación Evaluativa

| Ejecución práctica | x | Entrega de encargo | x | Presentación | x |
|-------------------|---|---|--------------------|---|---|--------------|---|

---

## 2. Instrucciones

### Descripción general de la evaluación

La evaluación consiste en realizar y presentar un informe de gestión de grandes volúmenes de Datos, mediante la carga histórica de todos los archivos disponibles, junto con información capturada en forma streaming/Real Time, la cual permita a los usuarios responder diversas preguntas de negocio relacionadas con la disponibilidad de servicios en ciertas zonas, horarios y frecuencia.

Adicionalmente, deberá diseñar y crear dos reportes que muestren información agregada.

**El propósito de esta evaluación es evaluar los siguientes Indicadores de Logro:**

- **IL 3.1** — Crea proceso de ingesta utilizando variedad de APIs disponibles en la industria para implementar procesos de ingesta de datos en línea.
- **IL 3.2** — Construye proceso, con el fin de realizar limpieza, transformación y almacenamiento de grandes volúmenes de datos en tiempo real/streaming.
- **IL 3.3** — Sintetiza la información en un panel de control para demostrar el potencial de la herramienta utilizada.

- Esta evaluación consiste en una **entrega de encargo con presentación** y tiene un **35%** de ponderación sobre la nota final de la asignatura.
- Tiempo asignado: **tres semanas** (Entrega de instrucciones la semana 14, entrega del informe el mismo día de la presentación, semana 17).
- Presentación/defensa: **10 minutos**, en parejas, en taller de alto cómputo.

| Evaluación           | % dentro de la asignatura | Tipo        | Distribución |
|----------------------|---------------------------|-------------|--------------|
| Evaluación Parcial 3 | 35%                       | A. Encargo  | 30%          |
|                      |                           | B. Present. | 70%          |

---

### Instrucciones Específicas

#### Dimensión encargo

Deberán construir procesos de carga, considerando disponibilidad de la información desde fuente de origen, en caso de errores. Construir procesos de transformación y limpieza de datos, dejando los datos en formatos para capa de consumo, evitando duplicidad de datos real time/Streaming para detección oportuna de errores.

- **Paso 1:** Realizar las conexiones con la fuente de origen de datos.
- **Paso 2:** Descargar y/o generar los archivos al data lake o fuente de destino. Utilizando las APIs disponibles o construidas por usted.
- **Paso 3:** Construir los procesos de limpieza, transformación y carga al modelo de datos final, considerando la trazabilidad de información y ciclo de vida del dato.
- **Paso 4:** Mejorar los reportes y/o visualizaciones correspondientes construidos previamente en la etapa 2.

Debe considerar: Reportes y/o visualizaciones correspondientes en un **panel o dashboard interactivo** (del cual debe incluir imágenes en el informe).

Para lo anterior, deberá realizar lo siguiente:

- Construir procesos de carga, considerando disponibilidad de la información desde fuente de origen, en caso de errores.
- Construir procesos de transformación y limpieza de datos, dejando los datos en formatos para capa de consumo, evitando duplicidad de datos tiempo real/Streaming para detección oportuna de errores.

Para cada uno de estos pasos, debe considerar (si aplica) lo siguiente:

- **Control de errores:** Todos los procesos pueden tener puntos de fallo, de acuerdo con lo identificado en la etapa 1 (diseño), debe implementar los controles de errores correspondientes.
- **Control de duplicidad de datos:** Considerar que los procesos se pueden ejecutar múltiples veces, y que los datos desde el origen pueden cambiar, por tanto, sus procesos deben determinar qué hacer si una ejecución devuelve datos que ya existen (tome la decisión de acuerdo con lo visto durante el semestre). También debe considerar que parte de estos datos pueden haber sido cargados desde la etapa 2 de datos Batch.
- **Registro de actividad:** Como se señaló anteriormente, los procesos se podrían ejecutar varias veces, debe incorporar el control de ejecución (ej.: ¿Si el proceso ya se ejecutó lo debo volver a ejecutar, lo debo bloquear o debo pedir autorización para volver a ejecutar?).
- **Validación de Datos y Procesos:** Según corresponda, debe considerar en su construcción la validación de los procesos y la validación de los datos a trabajar, incluyendo procesos de transformación, manteniendo la trazabilidad de los datos desde el origen.

#### Dimensión presentación

- Para la presentación, deberán simular una **entrega gerencial**, evaluada individualmente.
- Presenta el proceso de ingesta de datos utilizando variedad de APIs disponibles en la industria para implementar procesos de ingesta de datos en línea.
- Presenta la construcción del proceso, con el fin de realizar limpieza, transformación y almacenamiento de grandes volúmenes de datos en formato real-time/streaming.
- Presenta la síntesis de la información en un panel de control para demostrar el potencial de la herramienta utilizada.
- Presenta los resultados siguiendo una estructura lógica, considerando la información del informe.
- Deberá utilizar un lenguaje técnico propio de la disciplina, además de justificar y responder preguntas sobre cualquier aspecto trabajado.

> Aunque esta evaluación se desarrolla en duplas, la **calificación es de carácter individual** y responde al desempeño particular de cada integrante.

---

### Aspectos Formales

**Producto / Informe:**

- Subir a plataforma AVA
- Formato **.pdf** con un máximo de **10 páginas**, en fuentes Arial o Calibri, tamaño 10 a 12.
- Portada con detalle de sección, nombre y rut de los integrantes.
- Introducción
- Índice
- Desarrollo: Todos los apartados del encargo.
- Los trabajos entregados fuera de plazo serán calificados con nota **1.0**.

**Presentación:**

- Tiempo máximo: **10 minutos** + 5 minutos para preguntas.
- Máximo **10 láminas**; se recomienda el uso de plantillas interactivas, priorizando diagramas, flujo de procesos y tablas consolidadas.
- Diapositivas formales, correcta ortografía, colores adecuados, contenido sintético.
- Distribución equitativa del tiempo y trabajo entre los integrantes.
- Las preguntas pueden ser dirigidas a cualquier integrante.

**Anexos:** Se puede agregar como anexo o punto final los recursos que considere necesarios.

---

## 3. Pauta de Evaluación

Tipo de Pauta: **Rúbrica**

| Categoría               | % logro | Descripción                                                     |
|-------------------------|---------|-----------------------------------------------------------------|
| Muy buen desempeño      | 100%    | Desempeño destacado, logro de todos los aspectos evaluados.     |
| Buen desempeño          | 80%     | Alto desempeño con pequeñas omisiones, dificultades y/o errores.|
| Desempeño aceptable     | 60%     | Desempeño competente, logro de lo básico pero con omisiones.    |
| Desempeño incipiente    | 30%     | Omisiones importantes, no evidencia los elementos básicos.      |
| Desempeño no logrado    | 0%      | Ausencia o incorrecto desempeño.                                |

### Categorías de Respuesta

| Indicador de Evaluación | Muy buen desempeño (100%) | Buen desempeño (80%) | Desempeño aceptable (60%) | Desempeño incipiente (30%) | Desempeño no logrado (0%) | Ponderación |
|---|---|---|---|---|---|---|
| **Dimensión encargo** | | | | | | **30%** |
| 1. Crea proceso de ingesta utilizando variedad de APIs disponibles en la industria para implementar procesos de ingesta de datos en línea. | Crea proceso de ingesta utilizando variedad de APIs disponibles en la industria para implementar procesos de ingesta de datos en línea. | Crea proceso... pero con pequeñas omisiones. | Crea proceso... con omisiones, dificultades y/o errores. | Crea proceso... pero presenta omisiones, dificultades o errores significativos. | No crea proceso. | 10% |
| 2. Construye procesos, con el fin de realizar limpieza, transformación y almacenamiento de grandes volúmenes de datos en tiempo real/streaming. | Construye procesos de limpieza y transformación que consideren **cuatro aspectos**: normalización, agregación, enriquecimiento, validación, limpieza y deduplicación. | Considera solo **tres** aspectos. | Considera solo **dos** aspectos. | Considera solo **un** aspecto. | No construye estos procesos. | 10% |
| 3. Sintetiza la información en un panel de control para demostrar el potencial de la herramienta utilizada. | Panel interactivo que cumple **completamente** con: datos pertinentes, bien seleccionados, visualizaciones adecuadas, tendencias y patrones claros, interactivo y simple. | Cumple con la **mayoría** de las características. | Cumple con la **mitad** de las características. | Cumple con solo **algunas** características. | No cumple ninguna. | 10% |
| **Dimensión presentación** | | | | | | **70%** |
| 1. Demuestra dominio sobre la creación del proceso de ingesta... fundamentando con argumentos coherentes y propios de la disciplina. | Dominio completo y profundo, argumentos coherentes, detallados y bien fundamentados. | Dominio, aunque faltan algunos detalles o ejemplos. | Argumentos superficiales o parcialmente desarrollados. | Errores relevantes, argumentos superficiales. | No demuestra conocimiento. | 20% |
| 2. Demuestra dominio sobre la construcción del proceso de limpieza, transformación y almacenamiento en tiempo real/streaming... | Dominio completo y profundo, argumentos coherentes y detallados, terminología adecuada. | Dominio, aunque faltan algunos detalles o ejemplos. | Argumentos superficiales o parcialmente desarrollados. | Errores relevantes, argumentos superficiales, terminología inadecuada. | No demuestra conocimiento. | 25% |
| 3. Demuestra dominio en la síntesis de la información en un panel de control... | Dominio completo y profundo, argumentos coherentes y detallados, terminología adecuada. | Dominio, aunque faltan algunos detalles o ejemplos. | Argumentos superficiales o parcialmente desarrollados. | Errores relevantes, argumentos superficiales, terminología inadecuada. | No demuestra conocimiento. | 25% |
| **Total** | | | | | | **100%** |
