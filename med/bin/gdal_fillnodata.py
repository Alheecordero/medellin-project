#!/home/alhee/Desktop/DJ5_BOOK/Geodjango/geoapp/Poblado_medellin_app/med/bin/python3

import sys

from osgeo.gdal import UseExceptions, deprecation_warn

# import osgeo_utils.gdal_fillnodata as a convenience to use as a script
from osgeo_utils.gdal_fillnodata import *  # noqa
from osgeo_utils.gdal_fillnodata import main

UseExceptions()

deprecation_warn("gdal_fillnodata")
sys.exit(main(sys.argv))
