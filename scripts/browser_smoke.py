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
                # Cámara falsa de Chrome: permite probar la captura sin hardware ni diálogo de permisos.
                browser = playwright.chromium.launch(headless=True, executable_path=args.chrome, args=[
                    "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required"])
                page = browser.new_page(viewport={"width": 1440, "height": 1100})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                page.wait_for_selector('#live-sample-grid .sample-choice')

                # Llamada en vivo simulada con un deepfake: alerta, bloqueo y liberación controlada.
                page.locator('#live-sample-grid [data-sample="fake_01"]').click()
                page.locator('#live-consent').check()
                page.locator('#live-start').click()
                page.wait_for_selector('#incoming:not([hidden])')
                page.locator('#incoming-accept').click()
                page.wait_for_selector('#call-hud:not([hidden])')
                page.wait_for_function("document.querySelector('#live-badge').textContent === 'Posible deepfake'", timeout=60000)
                assert page.locator('#live-alert').is_visible()
                page.screenshot(path='/tmp/vericall_live_alert.png', full_page=True)
                page.locator('#live-transfer-form [name="analyst"]').fill('Ana Tesorería')
                page.locator('#live-transfer-form button[type="submit"]').click()
                page.wait_for_selector('#live-decisions .payment-decision.blocked')
                card = page.locator('#live-decisions .payment-decision').first
                card.locator('[name="actor"]').fill('Ana Tesorería')
                card.locator('[name="role"]').select_option('analista')
                card.locator('[data-outcome="release"]').click()
                card.locator('.form-error:not([hidden])').wait_for()
                assert 'seguridad' in card.locator('.form-error').inner_text()
                card.locator('[name="role"]').select_option('seguridad')
                card.locator('[name="actor"]').fill('Luis Seguridad')
                card.locator('[name="alternate_verified"]').check()
                card.locator('[name="channel"]').fill('Llamada al número registrado; el directivo no pidió el pago')
                card.locator('[data-outcome="reject"]').click()
                card.locator('.resolution-done.rejected').wait_for()
                page.locator('#live-end').click()
                page.wait_for_selector('#live-start:not([hidden])')
                assert not page.locator('#live-alert').is_visible()
                assert 'alerting' not in page.locator('#call-stage').get_attribute('class')
                page.wait_for_function("document.querySelector('#integrity-status').textContent.includes('íntegra')")
                page.screenshot(path='/tmp/vericall_live_decision.png', full_page=True)

                # Video propio como llamada entrante: se reproduce en el navegador y solo viajan cuadros.
                page.locator('#live-file').set_input_files({'name': 'mi_llamada.mp4', 'mimeType': 'video/mp4',
                                                            'buffer': (ROOT / 'sample_data/public/fake_01.mp4').read_bytes()})
                page.wait_for_function("document.querySelector('#live-file-name').textContent.includes('SHA-256')")
                assert page.locator('#live-sample-grid .sample-choice.selected').count() == 0
                page.locator('#live-start').click()
                page.locator('#incoming-accept').click()
                page.wait_for_selector('#call-hud:not([hidden])')
                page.wait_for_function("document.querySelector('#live-badge').textContent === 'Posible deepfake'", timeout=60000)
                assert 'mi_llamada.mp4' in page.locator('#call-events').inner_text()
                page.locator('#live-end').click()
                page.wait_for_selector('#live-start:not([hidden])')

                # Cámara: la imagen sintética de Chrome no tiene rostro y no debe producir autorización.
                page.locator('[data-source="camera"]').click()
                page.locator('#live-start').click()
                page.wait_for_selector('#call-hud:not([hidden])')
                page.wait_for_function("Number(document.querySelector('#live-frames').textContent) >= 3", timeout=30000)
                assert page.locator('#live-badge').inner_text() == 'Reuniendo evidencia'
                page.locator('#live-transfer-form button[type="submit"]').click()
                page.wait_for_function("document.querySelectorAll('#live-decisions .payment-decision').length === 2")
                assert 'otro canal' in page.locator('#live-decisions .payment-decision h3').first.inner_text()
                page.locator('#live-end').click()

                page.locator('#mode-recording').click()
                page.wait_for_selector('#sample-grid .sample-choice')
                assert page.locator('#sample-grid .sample-choice').count() == 6
                page.wait_for_function("document.querySelector('#preview').readyState >= 2")
                page.locator('#sample-grid [data-sample="fake_01"]').click()
                page.wait_for_function("document.querySelector('#preview').readyState >= 2")
                page.evaluate("document.querySelector('#preview').play()")
                page.wait_for_function("document.querySelector('#preview').currentTime > 0.1")
                page.evaluate("document.querySelector('#preview').pause()")
                page.locator('[name="consent"]').check()
                page.locator('#analyze-button').click()
                page.wait_for_selector('#result-panel:not([hidden])', timeout=120000)
                assert 'deepfake' in page.locator('#verdict-title').inner_text()
                assert page.locator('#recording-decision .resolution').is_visible()
                with page.expect_download() as download_info:
                    page.locator('#export-link').click()
                downloaded = Path(directory) / 'report.json'
                download_info.value.save_as(downloaded)
                report = json.loads(downloaded.read_text())
                assert report['detection']['predicted_label'] == 'fake'
                assert report['detection']['model']['executed'] is True
                page.screenshot(path='/tmp/vericall_desktop.png', full_page=True)

                page.locator('#sample-grid [data-sample="fake_04"]').click()
                page.locator('#analyze-button').click()
                page.wait_for_selector('#result-panel:not([hidden])', timeout=60000)
                assert 'no coincide' in page.locator('#reference-comparison').inner_text()

                # Comprueba que el video MOV también puede reproducirse en este navegador.
                page.locator('#sample-grid [data-sample="real_05"]').click()
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
                assert page.locator('#history-body tr').count() == 5
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path='/tmp/vericall_mobile.png', full_page=True)
                assert not errors, errors
                browser.close()
                print('PASS: llamada en vivo (alerta, bloqueo, regla de seguridad, rechazo), cámara sin rostro, '
                      'reproducción MP4/MOV, inferencia, caso fallado visible, carga propia, error, JSON, bitácora íntegra y vista móvil.', flush=True)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            app.extensions['vericall_jobs'].executor.shutdown(wait=True)


if __name__ == '__main__':
    main()
