#!/usr/bin/python3
# -*-coding:utf-8 -*
"""
 pyq-OSRM:

   N to N  |
   1 to N  | matrix of route (distance and time distance) between locations
   N to 1  |
   N to M  |

 Send multiple requests to an osrm local server in order to build a matrice
 of time/route_distance/euclidian_distance between a set of locations.

 The set of locations must be provided in .csv (first line as headers and only
 three columns : id, x and y in any kind of order) or a shapefile (the first
 field will be used as an unique ID)

 Output is a shapefile containing the geometry of the fastest route, the time
 in seconds, route distance (meters) and euclidian distance (meters) between
 each pair of locations.
 -----------------------------------------------------------------------------
 Usage :
   try --help to get some help
"""
# The MIT License (MIT)
#
#    « Copyright (c) 2015, mthh
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# pylint: disable=E0611, E1101, C0325

import csv
import json
import pyproj
import sys
import urllib.request
import os.path
from os import remove as removefile
from time import time
try:
    from osgeo import ogr, osr
except:
    import ogr
    import osr
from polyline.codec import PolylineCodec


def range2d(liste1, liste2):
    """
    Helper function to avoid nested loop in core code
        and only yield the 2 requested feature
    """
    for ft1 in liste1:
        for ft2 in liste2:
            yield ft1, ft2


def async_query_osrm_to_shp(dict_coord, coord_liste_s, coord_liste_t,
                            dstpath, host, concurrent_requests):
    """
    Fonction qui prend en entrée un dictionnaire de {'coordonnées':'noms'}
        et les listes de coordonées, envoie les requetes au serveur OSRM et
        enregistre le résultat dans le fichier de sortie indiqué (.shp).
    """
    try:
        from utils_pyqosrm import AsyncRoutesFetcher
    except:
        from .utils_pyqosrm import AsyncRoutesFetcher
    print("pyq-OSRM : {0} routes to calculate\n..."
          .format(len(coord_liste_s) * len(coord_liste_t)))

    urls = [
        '{0}/viaroute?loc={1}&loc={2}&instructions=false&alt=false'
        .format(host, source, target)
        for source, target
        in range2d(coord_liste_s, coord_liste_t)
        ]
    RouteFetcher = AsyncRoutesFetcher(
        urls, concurrent_requests, dstpath, dict_coord)
    res = RouteFetcher.run()
    return res


def query_osrm_to_shp(dict_coord, coord_liste_s, coord_liste_t, dstpath, host):
    """
    Fonction qui prend en entrée un dictionnaire de {'coordonnées':'noms'}
        et les listes de coordonées, envoie les requetes au serveur OSRM et
        enregistre le résultat dans le fichier de sortie indiqué (.shp).
    """
    testit, error = 0, 0
    # Syst de coord. a adopter pour écrire le fichier shp
    spatialreference = osr.SpatialReference()
    spatialreference.SetWellKnownGeogCS('WGS84')

    # Syst de coord. pour le calcul de la distance à vol d'oiseau
    geod = pyproj.Geod(ellps='WGS84')

    # Définition du type du fichier de sortie..
    driver = ogr.GetDriverByName("ESRI Shapefile")

    try:
        if os.path.exists(dstpath):
            removefile(dstpath)
        dstfile = driver.CreateDataSource(dstpath)
        dstlayer = dstfile.CreateLayer("layer", spatialreference)
    except Exception as err:
        print(err, "\nErreur lors de la création du fichier")
        sys.exit(0)
    # Ajout des champs à remplir et de leurs variables associées dans un dico
    # qui va permettre de faire une boucle sur ces éléments et éviter
    # de retaper ça lors de la création des champs :
    fields = [
        ['ID', {'type': ogr.OFTInteger, 'width': 10}],
        ['Total_time', {'type': ogr.OFTInteger, 'width': 14}],
        ['Total_dist', {'type': ogr.OFTInteger, 'width': 14}],
        ['Dist_eucl', {'type': ogr.OFTInteger, 'width': 14}],
        ['Src_name', {'type': ogr.OFTString, 'width': 80}],
        ['Tgt_name', {'type': ogr.OFTString, 'width': 80}]
        ]

    for field_name, detail in fields:
        fielddef = ogr.FieldDefn(field_name, detail['type'])
        fielddef.SetWidth(detail['width'])
        dstlayer.CreateField(fielddef)

    print("pyq-OSRM : {0} routes to calculate"
          .format(len(coord_liste_s) * len(coord_liste_t)))

    for source, target in range2d(coord_liste_s, coord_liste_t):
        src_name, tgt_name = dict_coord[source], dict_coord[target]
        # Préparation et envoi de la requete puis récupération de la réponse
        url_query = (
            '{0}/viaroute?loc={1}&loc={2}'
            '&instructions=false&alt=false'
            ).format(host, source, target)
        try:
            response = urllib.request.urlopen(url_query)
        except Exception as err:
            print("\npyq-OSRM :\nErreur lors du passage de l'URL\n", err)
            sys.exit(0)

        # Lecture des résultats (bytes) en json
        parsed_json = json.loads(response.readall().decode('utf-8'))

        # Calcul de la distance euclidienne entre l'origine et la destination
        _, _, distance_eucl = geod.inv(source[source.find(',') + 1:],
                                       source[:source.find(',')],
                                       target[target.find(',') + 1:],
                                       target[:target.find(',')])

        # Verification qu'une route a bien été trouvée par OSRM (si aucune
        # route n'a été trouvé une exception doit être levée quand on essai
        # de récupérer le temps total et le code erreur est lu dans le except):
        try:
            # Récupération des infos intéressantes...
            total_time_osrm = parsed_json['route_summary']['total_time']
            total_dist_osrm = parsed_json['route_summary']['total_distance']

            # ...dont la géométrie est au format encoded polyline algorythm,
            # à décoder pour obtenir la liste des points composant la ligne
            # La géométrie arrive sous forme de liste de points (lat, lng)
            epa_dec = PolylineCodec().decode(parsed_json['route_geometry'])
            ma_ligne = ogr.Geometry(ogr.wkbLineString)
            line_add_pts = ma_ligne.AddPoint_2D

            for coord in epa_dec:
                line_add_pts(coord[1]/10.0, coord[0]/10.0)

            # Ecriture de la geométrie et des champs
            feature = ogr.Feature(dstlayer.GetLayerDefn())
            feature.SetGeometry(ma_ligne)
            for f_name, f_value in zip(
                    ['ID', 'Total_time', 'Total_dist',
                     'Dist_eucl', 'Src_name', 'Tgt_name'],
                    [testit, total_time_osrm, total_dist_osrm,
                     distance_eucl, src_name, tgt_name]):
                feature.SetField(f_name, f_value)
            dstlayer.CreateFeature(feature)
#            print("Processing.... {0}%".format(int(
#                  testit / (len(coord_liste_s) * len(coord_liste_t)) * 100)),
#                  end='\r')
            testit += 1

        except KeyError:
            error += 1
            if parsed_json['status'] == 207:
                print("Err #{0}  : OSRM status 207 - "
                      "No route found between {1} and {2}"
                      .format(error, src_name, tgt_name))
            else:
                print("Err #{0}  : No route found between {1} and {2}"
                      .format(error, src_name, tgt_name))
    if error > 0:
        print("\t{0} route calculations failed".format(error))
    feature.Destroy()
    dstfile.Destroy()
    return testit


def read_row(file_path, ext):
    """
    Helper function to redirect to the correct way to read the input file.
        In both case it read the input file and return two objects : a list of
        concatenated coordinates as ['lat,long',
                                     'lat,lon',
                                     'lat,lon']  to feed the url query
        and a dict (thus keeping trace of the id/name of the feature)

    :param string file_path: The path of the file to read (both .csv and .shp
        are accepted)

    :param string ext: Extension as tree character
        (only 'csv' and 'shp' are excepected here)
    """
    return {'csv': read_csv, 'shp': read_shp}[ext](file_path)


def read_csv(file_path):
    my_dict = {}
    coord_liste = []
    with open(file_path, 'r') as opened_file:
        reader = csv.reader(opened_file)
        try:
            header = [i.lower() for i in next(reader)]
            x_col = [i for i, j in enumerate(header)
                     if ('x' in j or 'lon' in j)][0]
            y_col = [i for i, j in enumerate(header)
                     if ('y' in j or 'lat' in j)][0]
            id_col = min(
                [i for i, j in enumerate(header) if not
                 ('y' in j and 'x' in j and 'lat' in j and 'lon' in j)]
                )

            for row in reader:
                concat = row[y_col] + ',' + row[x_col]
                coord_liste.append(concat)
                my_dict[concat] = row[id_col]
        except csv.Error as err:
            sys.exit('Erreur dans la lecture du fichier csv : file {}, '
                     'line {}: {}'.format(file_path, reader.line_num, err))
    if len(coord_liste) < 1:
        sys.exit('Absence de données dans le fichier {}'.format(file_path))
    return my_dict, coord_liste


def read_shp(file_path):
    my_dict = {}
    coord_liste = []
    datasource = ogr.Open(file_path)
    layer = datasource.GetLayer(0)
    if layer.GetGeomType() != 1:
        sys.exit('Input shapefile must be a Points layer\n')
    for feature in layer:
        concat = str(feature.geometry().GetY()) \
            + ',' + str(feature.geometry().GetX())
        coord_liste.append(concat)
        my_dict[concat] = feature.GetField(0)

    return my_dict, coord_liste


def check_host(host):
    """ Helper function to get the hostname in desired format """
    if not ('http' in host and '//' in host) and host[len(host)-1] == '/':
        return ''.join(['http://', host[:len(host)-1]])
    elif not ('http' in host and '//' in host):
        return ''.join(['http://', host])
    elif host[len(host)-1] == '/':
        return host[:len(host)-1]
    else:
        return host

# pylint: disable=C0103
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description="pyq-osrm :\nPython script to query local osrm server and "
                    "return a shapefile containing the requested routes"
        )
    parser.add_argument(
        type=str, action='store', dest="filename",
        default="", help=".csv/.shp file to open"
        )
    parser.add_argument(
        '-m', '--one-to-many', dest='one_t', action='store_true', default=False,
        help="Calcul the fastest route between 1 source location and many "
             "destinations (default : Calcul fastest route between every "
             "locations provided in the dataset)"
        )
    parser.add_argument(
        '-t', '--many-to-one', dest='many_t', action='store_true', default=False,
        help="Calcul the fastest route between many sources locations and 1 "
             "same destination (default : Calcul fastest route between "
             "every locations provided in the dataset)"
        )
    parser.add_argument(
        '-d', '--different', dest='destinations_csv', action='store', default="",
        help="Different origins and destinations (put .csv / .shp file of "
             "destinations after this argument)"
        )
    parser.add_argument(
        '-o', '--output', dest='out_filename', action='store', default="",
        help="Change output name file (default : same name as the csv)"
        )
    parser.add_argument(
        '-H', '--host', dest='host', action='store', default="localhost:5000",
        help="Change the host where is located the OSRM instance "
             "(default : http://localhost:5000)")

    parser.add_argument(
        '-a', '--async', dest='concurrent_requests', action='store', default="",
        help="Choose non-blocking asynchronous requests with this option and "
             "set the number of maximum concurrent requests")

    args = parser.parse_args()
    start_time = time()

    if args.filename:
        if '.csv' not in str(args.filename)[-4:] \
                and '.shp' not in str(args.filename)[-4:]:
            print("Filename error : wrong format")
            sys.exit(0)
        elif not os.path.isfile(args.filename):
            print("\nErreur lors de l'ouverture du fichier\n")
            sys.exit(0)
    else:
        print("\nErreur lors de l'ouverture du fichier\n")
        sys.exit(0)

    dico, liste_ord = read_row(args.filename, args.filename[-3:])

    if args.out_filename:
        outfile = args.out_filename
        if '.shp' not in outfile[-4:]:
            outfile = outfile + '.shp'
    else:
        outfile = args.filename[:-4] + '-routes.shp'

    if args.one_t:
        coord_liste_t = [liste_ord[0]]
        liste_ord, coord_liste_t = coord_liste_t, liste_ord
        print("\nMode 1-to-Many\n")
    elif args.many_t:
        coord_liste_t = [liste_ord[0]]
        print("\nMode Many-to-1\n")
    elif args.destinations_csv:
        dico_suite, coord_liste_t = read_row(
            args.destinations_csv, args.destinations_csv[-3:])
        dico.update(dico_suite)
        print("\nMode N-to-M\n")
    else:
        coord_liste_t = liste_ord

    if args.concurrent_requests:
        try:
            import aiohttp
        except ImportError:
            print("\nLes bibliothèques asyncio et aiohttp sont nécessaires "
                  "pour le mode \"asynchrone\"\n")
            sys.exit(0)
        try:
            concurrent_requests = int(args.concurrent_requests)
        except:
            print("\nLe nombre de requête simultanées "
                  "doit être un nombre entier\n")
            sys.exit(0)

        nbw = async_query_osrm_to_shp(
            dico, liste_ord, coord_liste_t,
            outfile, check_host(args.host),
            concurrent_requests
            )

    else:
        nbw = query_osrm_to_shp(
            dico, liste_ord, coord_liste_t,
            outfile, check_host(args.host)
            )

    tt = time()-start_time
    print('  {} features written in {}\n{:.2f}s - {:.2f} routes/s'
          .format(nbw, outfile, tt, nbw/tt))
# pylint: enable=C0103,E0611, E1101, C0325
