cmake_minimum_required(VERSION 3.20.6...3.22.6 FATAL_ERROR)

project(CollaborativeVersioning)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "")
set(EXTENSION_CONTRIBUTORS "Ahmed Ben Akouche (ISIR)")
set(EXTENSION_DESCRIPTION "Collaborative versioning for 3D image annotations ...")
set(EXTENSION_ICONURL "https://www.example.com/Slicer/Extensions/CollaborativeVersioning.png")
set(EXTENSION_SCREENSHOTURLS "https://www.example.com/Slicer/Extensions/CollaborativeVersioning/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(CollaborativeVersioning)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
