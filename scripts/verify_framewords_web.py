"""Opt-in real website acceptance. Only self-authored synthetic media/text.

Default pytest never invokes live mode. Outputs stay under the ignored tmp/;
the report contains only versions, stages, sample IDs, digests and network
metadata. No traces, screenshots, HTML, response bodies or cookies are saved.
Explicitly generated .tkey files are sensitive acceptance artifacts.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = timezone(timedelta(hours=8))
sys.path.insert(0, str(ROOT / "src"))

from misong.carriers import DecodeRequest, EncodeRequest
from misong.carriers.framewords_web import FramewordsWebCarrier
from misong.text_contracts import ErrorCode, OperationContext, RuntimeSecrets, Stage, TextOperationError, text_digest


class AuditedCarrier(FramewordsWebCarrier):
    """Observe public version labels and request metadata, never request bodies."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.versions = set()
        self.browsers = set()
        self.destinations = Counter()
        self.non_get = 0
        self.query_requests = 0
        self.contexts = 0
        self.http_statuses = Counter()
        self._private_markers = ()
        self.literal_input_observed = False
        self.body_inspection_failed = False

    def watch_inputs(self, text, password, video_bytes):
        markers = [video_bytes]
        for value in (text, password):
            if value:
                markers.extend((value.encode('utf-8'), quote(value, safe='').encode('ascii'),
                                json.dumps(value, ensure_ascii=True)[1:-1].encode('ascii')))
        self._private_markers = tuple(markers)

    @asynccontextmanager
    async def _page(self):
        async with super()._page() as page:
            self.contexts += 1
            self.browsers.add(page.context.browser.version)
            def request_seen(request):
                parts = urlsplit(request.url)
                if parts.scheme not in ("http", "https"):
                    return
                # No path, query value, headers, request/response body or session.
                self.destinations[(parts.hostname or "", request.resource_type, request.method)] += 1
                self.non_get += request.method not in ("GET", "HEAD", "OPTIONS")
                self.query_requests += bool(parts.query)
                # Inspect in memory, persist booleans only. Literal matching does
                # not detect every possible encoding/encryption or prove privacy.
                try:
                    body = request.post_data_buffer or b''
                    url = request.url.encode('utf-8')
                    if any(marker in body or marker in url for marker in self._private_markers):
                        self.literal_input_observed = True
                except Exception:
                    self.body_inspection_failed = True
            page.on('request', request_seen)
            try:
                yield page
            finally:
                try:
                    # Only extract the public version, never keep the full DOM/body.
                    labels = await page.get_by_text(re.compile(r"^帧语\s+\d+\.\d+\.\d+$")).all_text_contents()
                    for label in labels:
                        match = re.fullmatch(r"帧语\s+(\d+\.\d+\.\d+)", label.strip())
                        if match:
                            self.versions.add(match[1])
                except Exception:
                    pass

    async def _open(self, page):
        page.on('response', lambda response: self.http_statuses.update([response.status]))
        await super()._open(page)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--live', action='store_true', help='required: access the real official website')
    result.add_argument('--work', type=Path, default=Path('tmp/framewords-smoke'), help='directory under ignored repository tmp/')
    result.add_argument('--browser', choices=('chromium', 'chrome', 'msedge'), default='chromium')
    result.add_argument('--headless', action='store_true', help='headless may receive an HTTP 403 challenge')
    result.add_argument('--timeout', type=float, default=600, help='maximum seconds per operation')
    result.add_argument('--samples', default='plain,unicode,beast,mojibake', help='subset of plain,unicode,beast,mojibake')
    result.add_argument('--ffmpeg', default=os.environ.get('MISONG_FFMPEG') or shutil.which('ffmpeg'))
    return result


def synthetic_video(path, ffmpeg):
    if not ffmpeg:
        raise TextOperationError(ErrorCode.UNSUPPORTED)
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
               'testsrc2=size=640x360:rate=30', '-t', '10', '-an', '-c:v', 'libx264',
               '-pix_fmt', 'yuv420p', '-n', str(path)]
    result = subprocess.run(command, capture_output=True, timeout=60,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode != 0:
        raise TextOperationError(ErrorCode.MEDIA)


def prepare_sample(name, password):
    from misong.text_layers import CarrierSpec, DeliveryRecipe, TextLayer
    from misong.text_pipeline import encode_text
    from misong import text_key
    original = ('  中文🙂 e\u0301\n虚构验收\t尾\n' if name == 'unicode'
                else 'https://example.invalid/s/c')
    layers = ()
    values = {}
    if name == 'beast':
        layers = (TextLayer('text', 'beast'),)
    if name == 'mojibake':
        layers = (TextLayer('text', 'mojibake', params={'mode': 'old'}, secret_slot='c/text'),)
        values['c/text'] = secrets.token_urlsafe(24)
    if password is not None:
        values['c/video'] = password
    recipe = DeliveryRecipe(1, 'c', 'synthetic acceptance', layers,
                            CarrierSpec('framewords', mode='standard', secret_slot='c/video' if password else None))
    context = OperationContext(secrets=RuntimeSecrets(values))
    try:
        result = encode_text(original, recipe, context)
        key_payload = text_key.build_payload(recipe, result, context)
    finally:
        context.secrets.clear()
    return original, result.text, key_payload


async def live(args, work):
    from misong import text_key
    from misong.text_restore import restore_text
    carrier = AuditedCarrier(browser=args.browser, headless=args.headless, timeout=args.timeout)
    source = work / 'synthetic-source.mp4'
    synthetic_video(source, args.ffmpeg)
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    report = {
        'date': datetime.now(SHANGHAI).isoformat(timespec='seconds'),
        'site': 'https://zy.lolcon.top/', 'mode': 'standard', 'profile': 'balanced',
        'browser_channel': args.browser, 'headless': args.headless,
        'playwright_version': importlib.metadata.version('playwright'),
        'material': 'self-authored testsrc2 640x360 30fps 10s, no audio',
        'samples': [], 'complete': False,
    }
    all_passed = True
    for name in args.samples.split(','):
        for protected in (False, True):
            sample_id = name + ('-password' if protected else '-plain')
            entry = {'id': sample_id, 'encode': 'not_run', 'saved_file_readback': 'not_run',
                     'independent_decode': 'not_run', 'tkey_restore': 'not_run'}
            report['samples'].append(entry)
            password = secrets.token_urlsafe(24) if protected else None
            stage = 'encode'
            payload = None
            recipient = None
            try:
                original, text, payload = prepare_sample(name, password)
                carrier.watch_inputs(text, password, source.read_bytes())
                entry['payload_sha256'] = text_digest(text)
                output = work / (sample_id + '.mp4')
                key = work / (sample_id + '.tkey')
                # Explicit --live acceptance includes exporting synthetic-only keys.
                text_key.write(key, payload)
                payload['secrets'].clear()
                payload = None
                def progress(event):
                    nonlocal stage
                    if event.stage == Stage.VERIFY:
                        entry['encode'] = 'passed'
                        stage = 'saved_file_readback'
                result = await carrier.encode(EncodeRequest(source, output, text, password=password),
                                              OperationContext(notify=progress))
                if not result.verified:
                    raise TextOperationError(ErrorCode.INTEGRITY)
                entry['encode'] = entry['saved_file_readback'] = 'passed'
                stage = 'independent_decode'
                # New carrier instance, new process-owned browser and context.
                recipient = AuditedCarrier(browser=args.browser, headless=args.headless, timeout=args.timeout)
                recipient.watch_inputs(text, password, output.read_bytes())
                decoded = await recipient.decode(DecodeRequest(output, password=password), OperationContext())
                if decoded.text != text:
                    raise TextOperationError(ErrorCode.INTEGRITY)
                entry['independent_decode'] = 'passed'
                stage = 'tkey_restore'
                if not carrier.capabilities().can_decode:
                    entry[stage] = 'not_run_unverified_capability'
                    all_passed = False
                else:
                    restored = await restore_text(text=None, video=output, key_file=key,
                                                  recipe=None, context=OperationContext(), carrier=carrier)
                    if not restored.verified or restored.text != original:
                        raise TextOperationError(ErrorCode.INTEGRITY)
                    entry[stage] = 'passed'
                    if name == 'plain' and protected:
                        stage = 'restore_retry_after_simulated_network_failure'
                        class OnceOffline:
                            calls = 0
                            def capabilities(self):
                                return carrier.capabilities()
                            async def decode(self, request, context):
                                self.calls += 1
                                if self.calls == 1:
                                    raise TextOperationError(ErrorCode.NETWORK)
                                return await carrier.decode(request, context)
                        retry = OnceOffline()
                        try:
                            await restore_text(text=None, video=output, key_file=key, recipe=None,
                                               context=OperationContext(), carrier=retry)
                        except TextOperationError as error:
                            if error.code != ErrorCode.NETWORK:
                                raise
                        else:
                            raise TextOperationError(ErrorCode.INTEGRITY)
                        restored = await restore_text(text=None, video=output, key_file=key, recipe=None,
                                                      context=OperationContext(), carrier=retry)
                        if not restored.verified or restored.text != original or retry.calls != 2:
                            raise TextOperationError(ErrorCode.INTEGRITY)
                        entry[stage] = 'passed'
                        entry['retry_scope'] = 'existing video+key only; no encode/upload/share call'
                if protected:
                    stage = 'wrong_password'
                    try:
                        await carrier.decode(DecodeRequest(output, password='synthetic-wrong-password'), OperationContext())
                    except TextOperationError as error:
                        if error.code not in (ErrorCode.WRONG_PASSWORD, ErrorCode.INTEGRITY):
                            raise
                        entry[stage] = 'passed'
                        entry['password_rejection_code'] = error.code.value
                    else:
                        raise TextOperationError(ErrorCode.INTEGRITY)
            except TextOperationError as error:
                entry[stage] = 'failed'
                entry['error_code'] = error.code.value
                all_passed = False
            except Exception:
                entry[stage] = 'failed'
                entry['error_code'] = ErrorCode.IO.value
                all_passed = False
            finally:
                if payload is not None:
                    payload['secrets'].clear()
                if recipient is not None:
                    carrier.versions.update(recipient.versions)
                    carrier.browsers.update(recipient.browsers)
                    carrier.destinations.update(recipient.destinations)
                    carrier.http_statuses.update(recipient.http_statuses)
                    carrier.non_get += recipient.non_get
                    carrier.query_requests += recipient.query_requests
                    carrier.literal_input_observed |= recipient.literal_input_observed
                    carrier.body_inspection_failed |= recipient.body_inspection_failed
                    recipient._private_markers = ()
                carrier._private_markers = ()
                password = None
            print(json.dumps(entry, ensure_ascii=True), flush=True)
            # Save a redacted partial report after every completed attempt.
            report.update(
                website_versions=sorted(carrier.versions), browser_versions=sorted(carrier.browsers),
                network=[{'host': k[0], 'type': k[1], 'method': k[2], 'count': v}
                         for k, v in sorted(carrier.destinations.items())],
                non_get_requests=carrier.non_get, requests_with_query=carrier.query_requests,
                http_statuses=dict(carrier.http_statuses),
                literal_input_observed=carrier.literal_input_observed,
                body_inspection_failed=carrier.body_inspection_failed,
                privacy='Outgoing bodies/URLs inspected in memory for literal inputs; only booleans saved. Other encodings/encryption can evade this check. No privacy guarantee.',
            )
            (work / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    report['source_unchanged'] = hashlib.sha256(source.read_bytes()).hexdigest() == source_digest
    report['complete'] = all_passed and report['source_unchanged']
    (work / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['complete'] else 1


def main():
    p = parser()
    args = p.parse_args()
    if not args.live:
        p.error('real website acceptance requires explicit --live; nothing was opened')
    if any(name not in ('plain', 'unicode', 'beast', 'mojibake') for name in args.samples.split(',')):
        p.error('unknown sample ID')
    base = args.work.resolve()
    if not base.is_relative_to((ROOT / 'tmp').resolve()):
        p.error('--work must stay under the repository ignored tmp/ directory')
    work = base / ('live-' + datetime.now(SHANGHAI).strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
    work.mkdir(parents=True)
    try:
        return asyncio.run(live(args, work))
    except TextOperationError as error:
        print(json.dumps({'error_code': error.code.value}), flush=True)
        return 1
    except Exception:
        print(json.dumps({'error_code': ErrorCode.IO.value}), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
