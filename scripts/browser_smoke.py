"""Prueba de interfaz con navegador real; usa una bitácora temporal aislada."""

import argparse
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from vericall.app import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", default=None, help="Ruta opcional del ejecutable de Chrome.")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vericall-browser-") as directory:
        app = create_app(Path(directory) / "audit.sqlite3")
        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, executable_path=args.chrome)
                page = browser.new_page(viewport={"width": 1440, "height": 1100})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                page.wait_for_selector('.sample-choice')
                assert page.locator('.sample-choice').count() == 6
                page.wait_for_function("document.querySelector('#preview').readyState >= 2")
                page.locator('[data-sample="fake_01"]').click()
                page.wait_for_function("document.querySelector('#preview').readyState >= 2")
                page.evaluate("document.querySelector('#preview').play()")
                page.wait_for_function("document.querySelector('#preview').currentTime > 0.1")
                page.evaluate("document.querySelector('#preview').pause()")
                page.locator('[name="consent"]').check()
                page.locator('#analyze-button').click()
                page.wait_for_selector('#result-panel:not([hidden])', timeout=120000)
                assert 'deepfake' in page.locator('#verdict-title').inner_text()
                with page.expect_download() as download_info:
                    page.locator('#export-link').click()
                downloaded = Path(directory) / 'report.json'
                download_info.value.save_as(downloaded)
                report = json.loads(downloaded.read_text())
                assert report['detection']['predicted_label'] == 'fake'
                assert report['detection']['model']['executed'] is True
                page.screenshot(path='/tmp/vericall_desktop.png', full_page=True)

                page.locator('[data-sample="fake_04"]').click()
                page.locator('#analyze-button').click()
                page.wait_for_selector('#result-panel:not([hidden])', timeout=60000)
                assert 'no coincide' in page.locator('#reference-comparison').inner_text()

                # Comprueba que el video MOV también puede reproducirse en este navegador.
                page.locator('[data-sample="real_05"]').click()
                page.wait_for_function("document.querySelector('#preview').readyState >= 2")
                page.locator('#upload-tab').click()
                page.locator('#video-file').set_input_files({
                    'name': 'original_real.mp4', 'mimeType': 'video/mp4',
                    'buffer': (ROOT / 'sample_data/public/fake_01.mp4').read_bytes()})
                page.locator('#analyze-button').click()
                page.wait_for_selector('#result-panel:not([hidden])', timeout=60000)
                assert 'deepfake' in page.locator('#verdict-title').inner_text()
                assert not page.locator('#reference-comparison').is_visible()

                page.locator('#video-file').set_input_files({'name': 'invalid.mp4', 'mimeType': 'video/mp4', 'buffer': b'text, not video'})
                page.locator('#analyze-button').click()
                page.wait_for_selector('#global-error:not([hidden])', timeout=30000)
                assert 'video válido' in page.locator('#global-error').inner_text()
                assert page.locator('#history-body tr').count() == 3
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path='/tmp/vericall_mobile.png', full_page=True)
                assert not errors, errors
                browser.close()
                print('PASS: reproducción MP4/MOV, inferencia, caso fallado visible, carga propia, error, JSON, historial y vista móvil.', flush=True)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            app.extensions['vericall_jobs'].executor.shutdown(wait=True)


if __name__ == '__main__':
    main()
