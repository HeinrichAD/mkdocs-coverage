"""This module contains the `mkdocs_coverage` plugin."""

from __future__ import annotations

import re
import shutil
import textwrap
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mkdocs.config.base import Config
from mkdocs.config.config_options import Optional
from mkdocs.config.config_options import Type as MkType
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files

from mkdocs_coverage.loggers import get_plugin_logger

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig

log = get_plugin_logger(__name__)


class MkDocsCoverageConfig(Config):
    """Configuration options for the plugin."""

    page_name = Optional(MkType(str, default=None))
    page_path = MkType(str, default="coverage")
    html_report_dir = MkType(str, default="htmlcov")


class MkDocsCoveragePlugin(BasePlugin[MkDocsCoverageConfig]):
    """The MkDocs plugin to integrate the coverage HTML report in the site."""

    def __init__(self) -> None:
        """Initialize the plugin."""
        super().__init__()
        self.page_path: str = ""

    def on_files(self, files: Files, config: MkDocsConfig, **kwargs: Any) -> Files:  # noqa: ARG002
        """Add the coverage page to the navigation.

        Hook for the [`on_files` event](https://www.mkdocs.org/user-guide/plugins/#on_files).
        This hook is used to add the coverage page to the navigation, using a temporary file.

        Arguments:
            files: The files collection.
            config: The MkDocs config object.
            **kwargs: Additional arguments passed by MkDocs.

        Returns:
            The modified files collection.
        """
        page_name = self.config.page_name
        page_path: str
        if page_name is not None:
            warnings.warn(
                "The 'page_name' configuration option is deprecated and will be removed in a future release. "
                "Use the 'page_path' configuration option instead.",
                DeprecationWarning,
                stacklevel=1,
            )
            page_path = page_name
        else:
            page_path = self.config.page_path
        self.page_path = page_path
        covindex = "covindex.html" if config.use_directory_urls else f"{page_path}/covindex.html"

        style = textwrap.dedent(
            """
            <style>
            article h1, article > a, .md-sidebar--secondary {
                display: none !important;
            }
            </style>
            """,
        )

        iframe = textwrap.dedent(
            f"""
            <iframe
                id="coviframe"
                src="{covindex}"
                frameborder="0"
                scrolling="no"
                onload="resizeIframe();"
                width="100%">
            </iframe>
            """,
        )

        script = textwrap.dedent(
            """
            <script>
            var coviframe = document.getElementById("coviframe");

            function resizeIframe() {
                coviframe.style.height = coviframe.contentWindow.document.documentElement.offsetHeight + 'px';
            }

            coviframe.contentWindow.document.body.onclick = function() {
                coviframe.contentWindow.location.reload();
            }
            </script>

            """,
        )
        page_contents = style + iframe + script
        files.append(
            File.generated(
                config=config,
                src_uri=page_path + ".md",
                content=page_contents,
            ),
        )
        return files

    def on_post_build(self, config: MkDocsConfig, **kwargs: Any) -> None:  # noqa: ARG002
        """Copy the coverage HTML report into the site directory.

        Hook for the [`on_post_build` event](https://www.mkdocs.org/user-guide/plugins/#on_post_build).

        Rename `index.html` into `covindex.html`.
        Replace every occurrence of `index.html` by `covindex.html` in the HTML files.

        Arguments:
            config: The MkDocs config object.
            **kwargs: Additional arguments passed by MkDocs.
        """
        site_dir = Path(config.site_dir)
        coverage_dir = site_dir / self.page_path
        tmp_index = site_dir / ".coverage-tmp.html"

        if config.use_directory_urls:
            shutil.move(str(coverage_dir / "index.html"), tmp_index)
        else:
            shutil.move(str(coverage_dir.with_suffix(".html")), tmp_index)

        shutil.rmtree(str(coverage_dir), ignore_errors=True)
        try:
            shutil.copytree(self.config.html_report_dir, str(coverage_dir))
        except FileNotFoundError:
            log.warning(f"No such HTML report directory: {self.config.html_report_dir}")
            return

        shutil.move(str(coverage_dir / "index.html"), coverage_dir / "covindex.html")

        if config.use_directory_urls:
            shutil.move(str(tmp_index), coverage_dir / "index.html")
        else:
            shutil.move(str(tmp_index), coverage_dir.with_suffix(".html"))

        for html_file in coverage_dir.iterdir():
            if html_file.suffix == ".html" and html_file.name != "index.html":
                html_file.write_text(re.sub(r'href="index\.html"', 'href="covindex.html"', html_file.read_text()))
