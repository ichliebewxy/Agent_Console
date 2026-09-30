"""OpenXML presentation access with conversion for legacy binary .ppt files."""

import os
import pathlib
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager


class PresentationReader:
    @contextmanager
    def open(self, file_path: str) -> Iterator[str]:
        with open(file_path, "rb") as source:
            signature = source.read(4)
        if signature.startswith(b"PK"):
            # A .ppt file may actually contain an OpenXML presentation.
            yield file_path
            return

        with tempfile.TemporaryDirectory(
            prefix="agent-console-ppt-", ignore_cleanup_errors=True
        ) as directory:
            root = pathlib.Path(directory)
            staged = root / "source.ppt"
            converted = root / "source.pptx"
            shutil.copy2(file_path, staged)
            attempts = []
            for name, converter in (
                ("Microsoft PowerPoint", self._convert_with_powerpoint),
                ("LibreOffice", self._convert_with_libreoffice),
            ):
                try:
                    converter(staged, converted)
                    if not converted.is_file():
                        raise RuntimeError("未生成 .pptx 文件")
                    break
                except Exception as exc:
                    attempts.append(f"{name}: {exc}")
                    converted.unlink(missing_ok=True)
            else:
                raise RuntimeError(
                    "无法解析旧版 .ppt 文件。请安装 Microsoft PowerPoint 或 LibreOffice，"
                    "也可以将文件另存为 .pptx 后重试。解析尝试："
                    + "; ".join(attempts)
                )
            yield str(converted)

    @staticmethod
    def _convert_with_powerpoint(source: pathlib.Path, target: pathlib.Path) -> None:
        if os.name != "nt":
            raise RuntimeError("Microsoft PowerPoint COM 仅适用于 Windows")
        try:
            import pythoncom
            from win32com.client import DispatchEx
        except ImportError as exc:
            raise RuntimeError("缺少 pywin32，无法调用 Microsoft PowerPoint") from exc

        pythoncom.CoInitialize()
        app = None
        presentation = None
        try:
            app = DispatchEx("PowerPoint.Application")
            try:
                app.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
            except Exception:
                pass
            presentation = app.Presentations.Open(
                str(source), ReadOnly=True, Untitled=False, WithWindow=False
            )
            presentation.SaveAs(str(target), 24)  # ppSaveAsOpenXMLPresentation
        finally:
            if presentation is not None:
                try:
                    presentation.Close()
                except Exception:
                    pass
            if app is not None:
                try:
                    app.Quit()
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    @staticmethod
    def _convert_with_libreoffice(source: pathlib.Path, target: pathlib.Path) -> None:
        executable = shutil.which("soffice") or shutil.which("libreoffice")
        if not executable:
            raise RuntimeError("未找到 LibreOffice")
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            [
                executable,
                "--headless",
                "--convert-to",
                "pptx",
                "--outdir",
                str(target.parent),
                str(source),
            ],
            capture_output=True,
            timeout=120,
            check=False,
            **kwargs,
        )
        if result.returncode != 0 or not target.is_file():
            detail = (result.stderr or result.stdout).decode(errors="replace").strip()
            raise RuntimeError(detail or f"LibreOffice 转换失败，退出码 {result.returncode}")
