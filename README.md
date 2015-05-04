# pyq-osrm

A simple python 3 script to query a local OSRM server API in order to get a distance/time matrix between a set of points and export all associated routes geometries in a shapefile.

This script use the great routing engine OSRM (https://github.com/Project-OSRM/), so it's supposed that you have an osrm server running locally (on http://localhost:5000/ ). It also requires that you have a python 3 interpreter installed/associated with your .py files.

It's a simple try to replicate the "http://localhost:5000/table?..." request (it only provides time between locations) by many "http://localhost:5000/viaroute?..." requests in order to obtain the geometry of each fastest route calculted.

## Requirement
Some python modules are needed :
* Polyline
* Osgeo
* Urllib
* Simanneal (only for the TSP script)

## Usage 
The input file must be a csv file (first line as headers) with comma separator in this format :
>    lat,long,name_of_the_place

(see the example.csv file)

The output file is a shapefile containing a line for each route (ie the fastest route between a couple of source/destination, calculated by OSRM) and following fields : the distance of road (in meters), the time on the road (on tenth of seconds), the euclidian distance (in meters), the name of the source and the name of the target.

The script can be called like this :
> pyqOSRM.py input_file.csv

or
> pyqOSRM.py input_file.csv -o output_file.shp

This script also allow you to make only a '1-to-many' calcul. The first location in the .csv file will be the only source point and others will be all the destinations. Just add the -m parameter at the end :
>	pyqOSRM.py input_file.csv -m

It is also possible to do the opposite calculation (many-to-one) by using the parameter -t :
> pyqOSRM.py input_file.csv -t

## Traveling salesman problem
On a side way, the pyq-osrm-tsp.py script try to implement the TSP (traveling salesman problem) with simulated annealing algorythm, based on calculations done by OSRM. It will requiere the python module «simanneal».
As in the first script, the input file must be a list of every locations in .csv format, where the first location will be the start (and end) point of the journey visiting each other location. Output is a shapefile.
> pyq-osrm-tsp.py input-file.csv -o output_filename

OSRM server has limitation concerning the number of locations supported in distance table query (default=100).
It can be raised when lauching the local server with argument –max-table-size, for example :
> osrm-routed.exe file.osrm –max-table-size=1234

Feel free to make any comment, this script is in its very early stage of development (many errors/exeptions are probably not yet handled).
