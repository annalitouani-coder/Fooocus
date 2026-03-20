import os
import args_manager
import modules.config
import json
import urllib.parse
import shared
from datetime import datetime
from urllib.parse import urlparse
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from modules.flags import OutputFormat
from modules.meta_parser import MetadataParser, get_exif
from modules.util import generate_temp_filename

log_cache = {}


def get_google_drive_path():
    possible_paths = [
        '/content/drive/MyDrive',
        '/mnt/drive',
        os.path.expanduser('~/GoogleDrive'),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None


def get_fooocus_gen_drive_path():
    drive_path = get_google_drive_path()
    if not drive_path:
        return None
    return os.path.join(drive_path, 'Colab Notebooks/fooocus_gen')


# ✅ Reusable save function (used for BOTH local + drive)
def save_image(image, path, output_format, parsed_parameters, metadata_parser):
    if output_format == OutputFormat.PNG.value:
        if parsed_parameters != '':
            pnginfo = PngInfo()
            pnginfo.add_text('parameters', parsed_parameters)
            pnginfo.add_text('fooocus_scheme', metadata_parser.get_scheme().value)
        else:
            pnginfo = None
        image.save(path, pnginfo=pnginfo)

    elif output_format == OutputFormat.JPEG.value:
        image.save(
            path,
            quality=95,
            optimize=True,
            progressive=True,
            exif=get_exif(parsed_parameters, metadata_parser.get_scheme().value)
            if metadata_parser else Image.Exif()
        )

    elif output_format == OutputFormat.WEBP.value:
        image.save(
            path,
            quality=95,
            lossless=False,
            exif=get_exif(parsed_parameters, metadata_parser.get_scheme().value)
            if metadata_parser else Image.Exif()
        )

    else:
        image.save(path)


def get_current_html_path(output_format=None):
    output_format = output_format if output_format else modules.config.default_output_format
    _, local_temp_filename, _ = generate_temp_filename(
        folder=modules.config.path_outputs,
        extension=output_format
    )
    return os.path.join(os.path.dirname(local_temp_filename), 'log.html')


def log(img, metadata, metadata_parser: MetadataParser | None = None,
        output_format=None, task=None, persist_image=True, session_id=None) -> str:

    path_outputs = modules.config.temp_path if args_manager.args.disable_image_log or not persist_image else modules.config.path_outputs
    output_format = output_format if output_format else modules.config.default_output_format

    date_string, local_temp_filename, only_name = generate_temp_filename(
        folder=path_outputs,
        extension=output_format
    )

    os.makedirs(os.path.dirname(local_temp_filename), exist_ok=True)

    parsed_parameters = metadata_parser.to_string(metadata.copy()) if metadata_parser else ''
    image = Image.fromarray(img)

    # ✅ session id from gradio url
    current_date = datetime.now().strftime("%Y%m%d")
    async_gradio_app = shared.gradio_root
    parsed_url = urlparse(str(async_gradio_app.share_url))
    session_id = parsed_url.hostname.split('.')[0]

    unique = f"foocus_{current_date}_{session_id}"

    # ✅ Save locally
    save_image(image, local_temp_filename, output_format, parsed_parameters, metadata_parser)

    if args_manager.args.disable_image_log:
        return local_temp_filename

    html_name = os.path.join(os.path.dirname(local_temp_filename), 'log.html')

    # ✅ Google Drive
    fooocus_gen_path = get_fooocus_gen_drive_path()

    drive_html_name = None
    drive_image_name = None

    if fooocus_gen_path:
        images_subfolder_path = os.path.join(fooocus_gen_path, unique)

        os.makedirs(images_subfolder_path, exist_ok=True)

        drive_html_filename = f"log_{unique}.html"
        drive_html_name = os.path.join(fooocus_gen_path, drive_html_filename)

        drive_image_name = os.path.join(
            images_subfolder_path,
            os.path.basename(local_temp_filename)
        )

        try:
            save_image(image, drive_image_name, output_format, parsed_parameters, metadata_parser)
            print(f"Image also saved to Google Drive at: {drive_image_name}")
        except Exception as e:
            print(f"Warning: Could not save image to Google Drive: {e}")

    # ✅ HTML
    css_styles = (
        "<style>"
        "body { background-color: #121212; color: #E0E0E0; } "
        "a { color: #BB86FC; } "
        ".metadata { border-collapse: collapse; width: 100%; } "
        ".metadata td { border: 1px solid #4d4d4d; padding: 4px; } "
        ".image-container img { max-width: 512px; display: block; } "
        "</style>"
    )

    begin_part = f"<!DOCTYPE html><html><head><title>Fooocus Log {date_string}</title>{css_styles}</head><body><!--fooocus-log-split-->\n"
    end_part = "</body></html>"

    middle_part = log_cache.get(html_name, "")

    item = f"<div><img src='{only_name}'><br>{only_name}</div>\n"
    middle_part = item + middle_part

    with open(html_name, 'w', encoding='utf-8') as f:
        f.write(begin_part + middle_part + end_part)

    if drive_html_name:
        try:
            with open(drive_html_name, 'w', encoding='utf-8') as f:
                f.write(begin_part + middle_part + end_part)
            print(f"HTML log also saved to Google Drive at: {drive_html_name}")
        except Exception as e:
            print(f"Warning: Could not save HTML to Google Drive: {e}")

    print(f"Image generated with private log at: {html_name}")

    log_cache[html_name] = middle_part

    return local_temp_filename
