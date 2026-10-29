"""Integrate text chains, explicit keys and optional video backends.

Returns artifact metadata only. Publish checkpoints and GUI recipe editing are
separate clients of this service; runtime requests must never be serialized.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict
from pathlib import Path

from . import text_key
from .carriers import EncodeRequest
from .jobs import fingerprint
from .text_contracts import (
    ErrorCode, OperationContext, RuntimeSecrets, Stage, TextOperationError, text_digest,
)
from .text_layers import DeliveryRecipe, MAX_TEXT_BYTES, validate_recipes
from .text_pipeline import decode_text, encode_text
from .text_restore import restore_text


def create_carrier():
    # Plain text commands must work without Playwright or network access.
    from .carriers.framewords_web import FramewordsWebCarrier
    return FramewordsWebCarrier()


def capabilities() -> dict:
    video = asdict(create_carrier().capabilities())
    return {"recipe_version": 1, "carriers": [
        {"format_id": "text", "backend_id": "local", "modes": ["plain"],
         "can_encode": True, "can_decode": True, "requires_network": False,
         "supports_password": False, "max_utf8_bytes": MAX_TEXT_BYTES}, video,
    ]}


def parse_recipes(data) -> tuple[DeliveryRecipe, ...]:
    if not isinstance(data, list) or not data:
        raise TextOperationError(ErrorCode.INVALID_RECIPE)
    return validate_recipes([DeliveryRecipe.from_dict(item) for item in data])


def preview(text: str, recipes: tuple[DeliveryRecipe, ...], *, carrier=None) -> dict:
    if not isinstance(text, str):
        raise TextOperationError(ErrorCode.INVALID_RECIPE)
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise TextOperationError(ErrorCode.CAPACITY)
    validate_recipes(recipes)
    result = []
    for recipe in recipes:
        video = recipe.carrier.format_id != "text"
        caps = (carrier or create_carrier()).capabilities() if video else None
        if caps is not None and (not caps.can_encode or caps.format_id != recipe.carrier.format_id
                                 or recipe.carrier.mode not in caps.modes
                                 or recipe.carrier.secret_slot and not caps.supports_password):
            raise TextOperationError(ErrorCode.UNSUPPORTED)
        result.append({"recipe_id": recipe.id, "needs_secrets": [
            item.secret_slot for item in (*recipe.layers, recipe.carrier) if item.secret_slot],
            "capacity_known": not video, "requires_network": bool(caps and caps.requires_network)})
    return {"recipes": result}


def read_text_file(path: Path) -> str:
    # read_bytes preserves CR/LF; pathlib.read_text performs newline translation.
    data = Path(path).open("rb")
    with data:
        raw = data.read(MAX_TEXT_BYTES + 1)
    if len(raw) > MAX_TEXT_BYTES:
        raise TextOperationError(ErrorCode.CAPACITY)
    return raw.decode("utf-8")


def _write_text(path: Path, text: str, context: OperationContext) -> None:
    context.check()
    created = False
    try:
        with path.open("xb") as stream:
            created = True
            stream.write(text.encode("utf-8"))
        context.check()
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise


async def deliver_recipe(text: str, recipe: DeliveryRecipe, destination: Path,
                         context: OperationContext, *, source: Path | None = None,
                         export_key: bool = False, carrier=None) -> dict:
    """One recipe, exclusive output directory. Successes survive other failures."""
    payload = None
    created = False
    owned = []
    code = None
    destination = Path(destination)
    try:
        context.check()
        preview(text, (recipe,), carrier=carrier)
        if type(export_key) is not bool:
            raise TextOperationError(ErrorCode.INVALID_RECIPE)
        if recipe.carrier.secret_slot:
            context.secrets.require(recipe.carrier.secret_slot)
        result = encode_text(text, recipe, context)
        # Verify this exact generated ciphertext, never regenerate it.
        restored = decode_text(result.text, recipe, result.receipts, context)
        if restored.text != text:
            raise TextOperationError(ErrorCode.INTEGRITY)
        video = recipe.carrier.format_id != "text"
        if video and source is None:
            raise TextOperationError(ErrorCode.MEDIA)
        destination.mkdir(parents=True, exist_ok=False)
        created = True
        artifact = destination / ("message.mp4" if video else "message.txt")
        owned.append(artifact)
        if video:
            backend = carrier or create_carrier()
            slot = recipe.carrier.secret_slot
            password = context.secrets.require(slot) if slot else None
            outer = OperationContext(RuntimeSecrets(), context.cancel, context.deadline, context.notify)
            encoded = await backend.encode(EncodeRequest(Path(source), artifact, result.text,
                                                        recipe.carrier.mode, password), outer)
            if (encoded.path.resolve() != artifact.resolve() or not artifact.is_file()
                    or not encoded.verified or encoded.payload_sha256 != text_digest(result.text)):
                raise TextOperationError(ErrorCode.INTEGRITY)
        else:
            _write_text(artifact, result.text, context)
        files = [{"role": "video" if video else "text", **fingerprint(artifact)}]
        if export_key:
            context.report(Stage.KEY_EXPORT)
            payload = text_key.build_payload(recipe, result, context)
            key_path = destination / "message.tkey"
            owned.append(key_path)
            text_key.write(key_path, payload)
            files.append({"role": "text_key", **fingerprint(key_path)})
        context.check()
        output = {"recipe_id": recipe.id, "status": "complete", "verified": True, "files": files}
    except TextOperationError as error:
        code = error.code
    except asyncio.CancelledError:
        code = ErrorCode.CANCELLED
    except (OSError, UnicodeError):
        code = ErrorCode.IO
    except Exception:
        code = ErrorCode.INTEGRITY
    finally:
        if payload is not None:
            payload["secrets"].clear()
        if code is not None and created:
            # Only files reserved by this invocation; never recurse over input.
            for path in owned:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                destination.rmdir()
            except OSError:
                pass
    if code is not None:
        raise TextOperationError(code)
    return output


async def _deliver_text(text: str, recipes: tuple[DeliveryRecipe, ...], output_dir: Path,
                       context: OperationContext, *, video_sources=None,
                       export_keys=(), carrier=None) -> dict:
    context.check()
    preview(text, recipes, carrier=carrier)
    if (not isinstance(export_keys, (list, tuple)) or any(not isinstance(v, str) for v in export_keys)
            or set(export_keys) - {r.id for r in recipes}):
        raise TextOperationError(ErrorCode.INVALID_RECIPE)
    # Case-insensitive file systems must not alias two recipe directories.
    if len({r.id.casefold() for r in recipes}) != len(recipes):
        raise TextOperationError(ErrorCode.INVALID_RECIPE)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    output = []
    for recipe in recipes:
        source = (video_sources or {}).get(recipe.id)
        output.append(await deliver_recipe(text, recipe, output_dir / recipe.id, context,
                                           source=Path(source) if source else None,
                                           export_key=recipe.id in export_keys, carrier=carrier))
    return {"out": str(output_dir), "recipes": output}


async def deliver_text(text: str, recipes: tuple[DeliveryRecipe, ...], output_dir: Path,
                       context: OperationContext, *, video_sources=None,
                       export_keys=(), carrier=None) -> dict:
    code = None
    try:
        output = await _deliver_text(text, recipes, output_dir, context, video_sources=video_sources,
                                     export_keys=export_keys, carrier=carrier)
    except TextOperationError as error:
        code = error.code
    except asyncio.CancelledError:
        code = ErrorCode.CANCELLED
    except (OSError, UnicodeError):
        code = ErrorCode.IO
    except Exception:
        code = ErrorCode.INVALID_RECIPE
    if code is not None:
        raise TextOperationError(code)
    return output


async def restore_to_file(destination: Path, *, context: OperationContext, **kwargs) -> dict:
    code = None
    try:
        if kwargs.get("video") is not None and kwargs.get("carrier") is None:
            kwargs["carrier"] = create_carrier()
        result = await restore_text(context=context, **kwargs)
        destination = Path(destination)
        _write_text(destination, result.text, context)
        output = {"out": str(destination), "verified": result.verified,
                  "original_sha256": result.original_sha256}
    except TextOperationError as error:
        code = error.code
    except asyncio.CancelledError:
        code = ErrorCode.CANCELLED
    except (OSError, UnicodeError):
        code = ErrorCode.IO
    except Exception:
        code = ErrorCode.INTEGRITY
    if code is not None:
        raise TextOperationError(code)
    return output


async def deliver_shared(plan: dict, text: str, folder: Path, context: OperationContext,
                         checkpoint, *, video_sources=None, export_keys=(), carrier=None) -> list[dict]:
    """Checkpoint each recipe after sharing; never invokes upload or share."""
    from .jobs import verify_files
    recipes = parse_recipes(plan["text_recipes"])
    ids = {r.id for r in recipes}
    if not isinstance(export_keys, (list, tuple)) or set(export_keys) - ids:
        raise TextOperationError(ErrorCode.INVALID_RECIPE)
    state = plan.setdefault("text_delivery", {"version": 1, "share_complete": True, "recipes": []})
    digest = text_digest(text)
    if state.get("source_sha256", digest) != digest:
        raise TextOperationError(ErrorCode.INTEGRITY)
    state["source_sha256"] = digest
    records = {r["recipe_id"]: r for r in state["recipes"]}
    first_error = None
    for recipe in recipes:
        record = records.get(recipe.id)
        if record is None:
            record = {"recipe_id": recipe.id, "status": "pending", "artifacts": [], "error_code": None}
            state["recipes"].append(record)
        try:
            context.check()
            if record["status"] == "complete":
                # Changed/missing deliveries require intervention, never a silent overwrite.
                verify_files(record["artifacts"])
                continue
            record.update(status="running", error_code=None)
            checkpoint()
            source = (video_sources or {}).get(recipe.id)
            result = await deliver_recipe(text, recipe, Path(folder) / (recipe.id + "-" + uuid.uuid4().hex[:12]),
                                          context, source=Path(source) if source else None,
                                          export_key=recipe.id in export_keys, carrier=carrier)
            record.update(status="complete", artifacts=result["files"], error_code=None)
            checkpoint()
        except TextOperationError as error:
            code = error.code
        except (OSError, ValueError):
            code = ErrorCode.IO
        else:
            continue
        record.update(status="cancelled" if code == ErrorCode.CANCELLED else "blocked", error_code=code.value)
        checkpoint()
        first_error = first_error or code
        if code == ErrorCode.CANCELLED:
            break
    if first_error is not None:
        raise TextOperationError(first_error)
    return state["recipes"]
