#-----------------------------------------------------------------------------
set(MODULE_NAME CollaborativeVersioning)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  CollaborativeVersioningLib/__init__.py
  CollaborativeVersioningLib/DataManager.py
  CollaborativeVersioningLib/VersionControlClient.py
  CollaborativeVersioningLib/OntologyLoader.py
  CollaborativeVersioningLib/GraphCanvas.py
  CollaborativeVersioningLib/UiStyles.py
  )

set(MODULE_PYTHON_RESOURCES
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
