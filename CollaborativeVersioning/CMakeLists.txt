#-----------------------------------------------------------------------------
set(MODULE_NAME CollaborativeVersioning)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  CollaborativeVersioningLib/__init__.py
  CollaborativeVersioningLib/DataManager.py
  CollaborativeVersioningLib/GitHubAuth.py
  CollaborativeVersioningLib/OntologyLoader.py
  CollaborativeVersioningLib/GraphCanvas.py
  CollaborativeVersioningLib/UiStyles.py
  CollaborativeVersioningLib/ModuleConstants.py
  CollaborativeVersioningLib/QtHelpers.py
  CollaborativeVersioningLib/Helpers.py
  CollaborativeVersioningLib/Dialogs.py
  CollaborativeVersioningLib/Widget.py
  CollaborativeVersioningLib/Logic.py
  )

set(MODULE_PYTHON_RESOURCES
  CollaborativeVersioningLib/down-arrow.svg
  CollaborativeVersioningLib/down-arrow-light.svg
  CollaborativeVersioningLib/notification-bell.svg
  CollaborativeVersioningLib/notification-bell-light.svg
  CollaborativeVersioningLib/ontologies/Allen_Mouse_Brain_Atlas.json
  CollaborativeVersioningLib/ontologies/Allen_Human_Brain_Atlas.json
  )

#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  WITH_GENERIC_TESTS
  )

#-----------------------------------------------------------------------------
if(BUILD_TESTING)

  slicer_add_python_unittest(SCRIPT ${MODULE_NAME}.py)

  add_subdirectory(Testing)
endif()
