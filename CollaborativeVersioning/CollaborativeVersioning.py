import importlib
import logging
import sys

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.i18n import translate

import CollaborativeVersioningLib
import CollaborativeVersioningLib.GraphCanvas
import CollaborativeVersioningLib.UiStyles

# Change this string to verify that Reload picked up your edits.
from CollaborativeVersioningLib.ModuleConstants import _UI_BUILD_TAG  # noqa: F401

_LIB_MODULE_NAMES = (
    "CollaborativeVersioningLib.UiStyles",
    "CollaborativeVersioningLib.DataManager",
    "CollaborativeVersioningLib.SegmentationCubes",
    "CollaborativeVersioningLib.GitHubAuth",
    "CollaborativeVersioningLib.OntologyLoader",
    "CollaborativeVersioningLib.GraphCanvas",
    "CollaborativeVersioningLib.ModuleConstants",
    "CollaborativeVersioningLib.QtHelpers",
    "CollaborativeVersioningLib.Helpers",
    "CollaborativeVersioningLib.Dialogs",
    "CollaborativeVersioningLib.Widget",
    "CollaborativeVersioningLib.Logic",
    "CollaborativeVersioningLib",
)


def _refreshLibModules() -> None:
    for module_name in _LIB_MODULE_NAMES:
        module = sys.modules.get(module_name)
        if module is not None:
            importlib.reload(module)


_refreshLibModules()

from CollaborativeVersioningLib.UiStyles import (  # noqa: E402,F401
    ACCENT_ICE,
    ACCENT_MINT,
    BG_ELEVATED,
    BORDER,
    BTN_CONNECT,
    BTN_CREATE,
    BTN_DELETE,
    BTN_DEPENDENCY,
    BTN_HISTORY,
    BTN_PEOPLE,
    BTN_PULL,
    BTN_PUSH,
    BTN_SAVE_VERSION,
    BTN_SECONDARY,
    BTN_NOTIFICATIONS,
    CHECKED_OUT_LABEL_STYLE,
    DIALOG_HINT_STYLE,
    DOCK_LOCK_BANNER_STYLE,
    DOCK_BTN_LOCKED_STYLE,
    DOCK_LOCKED_STYLE,
    DOCK_STYLE,
    DOCK_WIDGET_LOCKED_STYLE,
    FEED_COLOR_ERROR,
    FEED_COLOR_INFO,
    FEED_LOCKED_STYLE,
    FEED_STYLE,
    FIELD_STYLE,
    MESSAGES_HEADER_STYLE,
    MESSAGES_VIEW_STYLE,
    NOTIFICATIONS_BADGE_STYLE,
    PLACEHOLDER_LOCKED_STYLE,
    PLACEHOLDER_STYLE,
    SECTION_TITLE_LOCKED_STYLE,
    SECTION_TITLE_STYLE,
    SEPARATOR_STYLE,
    STATUS_NEUTRAL,
    STATUS_OK,
    TABLE_LOCKED_STYLE,
    TABLE_STYLE,
    TEXT_MUTED,
    TEXT_ON_ICE,
    TEXT_SECONDARY,
    notification_bell_url,
)

_STYLE_EXPORTS = (
    "ACCENT_ICE",
    "ACCENT_INDIGO",
    "ACCENT_MINT",
    "BG_ELEVATED",
    "BORDER",
    "BTN_CONNECT",
    "BTN_CREATE",
    "BTN_DELETE",
    "BTN_DEPENDENCY",
    "BTN_HISTORY",
    "BTN_PEOPLE",
    "BTN_PULL",
    "BTN_PUSH",
    "BTN_SAVE_VERSION",
    "BTN_SECONDARY",
    "BTN_NOTIFICATIONS",
    "CHECKED_OUT_LABEL_STYLE",
    "DIALOG_HINT_STYLE",
    "DOCK_LOCK_BANNER_STYLE",
    "DOCK_BTN_LOCKED_STYLE",
    "DOCK_LOCKED_STYLE",
    "DOCK_STYLE",
    "DOCK_WIDGET_LOCKED_STYLE",
    "FEED_COLOR_ERROR",
    "FEED_COLOR_INFO",
    "FEED_LOCKED_STYLE",
    "FEED_STYLE",
    "FIELD_STYLE",
    "MESSAGES_HEADER_STYLE",
    "MESSAGES_VIEW_STYLE",
    "NOTIFICATIONS_BADGE_STYLE",
    "PLACEHOLDER_LOCKED_STYLE",
    "PLACEHOLDER_STYLE",
    "SECTION_TITLE_LOCKED_STYLE",
    "SECTION_TITLE_STYLE",
    "SEPARATOR_STYLE",
    "STATUS_NEUTRAL",
    "STATUS_OK",
    "TABLE_LOCKED_STYLE",
    "TABLE_STYLE",
    "TEXT_MUTED",
    "TEXT_ON_ICE",
    "TEXT_SECONDARY",
)


def _bindIceClinicTheme() -> None:
    from CollaborativeVersioningLib import UiStyles

    UiStyles.apply_theme()
    module_globals = globals()
    for name in _STYLE_EXPORTS:
        module_globals[name] = getattr(UiStyles, name)


# Re-export split pieces so Reload / external refs keep working.
from CollaborativeVersioningLib.ModuleConstants import *  # noqa: E402,F401,F403
from CollaborativeVersioningLib.QtHelpers import *  # noqa: E402,F401,F403
from CollaborativeVersioningLib.Helpers import *  # noqa: E402,F401,F403
from CollaborativeVersioningLib.Dialogs import *  # noqa: E402,F401,F403
from CollaborativeVersioningLib.Widget import CollaborativeVersioningWidget  # noqa: E402
from CollaborativeVersioningLib.Logic import CollaborativeVersioningLogic  # noqa: E402

class CollaborativeVersioning(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Collaborative Versioning")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Informatics")]
        self.parent.dependencies = []
        self.parent.contributors = ["Ahmed Ben Akouche (ISIR)", "Julien Gori (CNRS)"]
        self.parent.helpText = _(
            """
            Collaborative versioning for 3D image annotations — UI MVP.<br><br>
            Connect with GitHub, then create or open a project.<br>
            Right panel: graphs, history, and activity feed.
            """
        )
        self.parent.acknowledgementText = _("ISIR/ICM project — collaborative 3D annotation versioning.")


class CollaborativeVersioningTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_WidgetBuildTagPresent()

    def test_WidgetBuildTagPresent(self):
        self.assertTrue(_UI_BUILD_TAG.startswith("2026-"))
        self.delayDisplay("CollaborativeVersioning UI layout tests passed")

