# The upstream underdongle module registers a library even when its shield is
# disabled. Zephyr already excludes empty libraries; declare this one intentional
# only in that configuration. Keep the module and its shield available for dongle
# builds, and never mask warnings for a populated or enabled dongle library.
if(NOT CONFIG_SHIELD_UNDERDONGLE_ADAPTER)
  get_property(molekula_libraries GLOBAL PROPERTY ZEPHYR_LIBS)
  foreach(molekula_library IN LISTS molekula_libraries)
    if(molekula_library MATCHES "(^|__)zmk-component-underdongle$")
      get_target_property(molekula_sources ${molekula_library} SOURCES)
      if(NOT molekula_sources)
        set_property(TARGET ${molekula_library} PROPERTY ALLOW_EMPTY TRUE)
      endif()
    endif()
  endforeach()
endif()
