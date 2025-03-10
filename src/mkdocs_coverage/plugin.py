"""This module contains the `mkdocs_coverage` plugin."""

from __future__ import annotations

import re
import shutil
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from mkdocs.config.base import Config
from mkdocs.config.config_options import Optional as MkOptional
from mkdocs.config.config_options import Type as MkType
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import File, Files

from mkdocs_coverage.loggers import get_plugin_logger

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig

log = get_plugin_logger(__name__)


class MkDocsCoverageConfig(Config):
    """Configuration options for the plugin."""

    page_path = MkType(str, default="coverage")
    html_report_dir = MkType(str, default="htmlcov")
    hide_page_title = MkOptional(MkType(bool))  # default: None
    coverage_inplace_placeholder = MkType(str, default="{{mkdocs-coverage}}")


class MkDocsCoveragePlugin(BasePlugin[MkDocsCoverageConfig]):
    """The MkDocs plugin to integrate the coverage HTML report in the site."""

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
        covindex = "covindex.html" if config.use_directory_urls else f"{self.config.page_path}/covindex.html"
        original_coverage_file = files.get_file_from_path(self.config.page_path + ".md")
        original_coverage_file_content = original_coverage_file.content_string if original_coverage_file else None

        page_content = self._build_coverage_page(covindex, original_coverage_file_content)
        files.append(
            File.generated(
                config=config,
                src_uri=self.config.page_path + ".md",
                content=page_content,
            ),
        )
        return files

    def _build_coverage_page(self, covindex: str, page_content: Optional[str]) -> str:
        """Build coverage page content.

        Method to build the coverage page content w.r.t. possible user-defined coverage file content.

        Arguments:
            covindex: File path to covindex.html.
            page_content: Page content of existing coverage file.

        Returns:
            The coverage page content.
        """
        hide_title = self.config.hide_page_title
        if hide_title is None:
            # by default hide title if there is no user-defined coverage page content
            hide_title = not bool(page_content)

        style = textwrap.dedent(
            """
            <style>
            article h1, article > a, .md-sidebar--secondary {
                display: none !important;
            }
            </style>
            """,
        ) if hide_title else ""
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

        coverage_page_content = style + iframe + script
        if not page_content:
            return coverage_page_content
        if page_content.__contains__(self.config.coverage_inplace_placeholder):
            return page_content.replace(self.config.coverage_inplace_placeholder, coverage_page_content)
        return page_content + "\n\n" + coverage_page_content

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
        coverage_dir = site_dir / self.config.page_path
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
