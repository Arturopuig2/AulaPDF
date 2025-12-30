# Aula PDF Reader

Una aplicación web desarrollada con FastAPI para gestionar y visualizar libros de texto en formato PDF de manera segura.

## Características

*   **Visor de PDF Seguro**: Los archivos PDF se sirven a través de un visor protegido que impide la descarga directa fácil.
*   **Panel de Administración**: Sube, gestiona y elimina PDFs.
*   **Códigos de Acceso**: Cada PDF tiene un código de acceso único.
*   **Protección por Contraseña**: Requiere autenticación para acceder al panel de administración.
*   **Diseño Responsivo**: Funciona en ordenadores y tabletas.

## Requisitos

*   Python 3.9+
*   Pip

## Instalación

1.  **Clonar el repositorio:**

    ```bash
    git clone https://github.com/tu-usuario/AulaPDF.git
    cd AulaPDF
    ```

2.  **Crear y activar un entorno virtual:**

    ```bash
    python -m venv venv
    
    # En Mac/Linux:
    source venv/bin/activate
    
    # En Windows:
    .\venv\Scripts\activate
    ```

3.  **Instalar dependencias:**

    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurar variables de entorno:**
    Crea un archivo `.env` en la raíz del proyecto copiando el ejemplo o con el siguiente contenido:

    ```ini
    SECRET_KEY=tu-clave-secreta-segura
    ADMIN_PASSWORD=tu-contraseña-admin
    ```

## Ejecución

Para iniciar el servidor de desarrollo:

```bash
uvicorn app.main:app --reload
```

La aplicación estará disponible en: `http://127.0.0.1:8000`

## Uso

1.  Ve a `http://127.0.0.1:8000/admin`.
2.  Inicia sesión con el usuario `admin` y la contraseña que definiste en `.env` (por defecto `admin123`).
3.  Sube tus archivos PDF.
4.  Comparte el enlace del visor o el código de acceso con tus alumnos.

## Licencia

Este proyecto está bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.
