# -*-coding:utf-8 -*

##    The MIT License (MIT)
##
##    « Copyright (c) 2015, mthh
##
##    Permission is hereby granted, free of charge, to any person obtaining a copy
##    of this software and associated documentation files (the "Software"), to deal
##    in the Software without restriction, including without limitation the rights
##    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
##    copies of the Software, and to permit persons to whom the Software is
##    furnished to do so, subject to the following conditions:
##
##    The above copyright notice and this permission notice shall be included in all
##    copies or substantial portions of the Software.
##
##    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
##    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
##    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
##    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
##    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
##    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
##    SOFTWARE.


##-----------------------------------------------------------------------------------
## pyq-OSRM:
##-----------------------------------------------------------------------------------
##   N to N  |
##   1 to N  | matrix of route (distance and time distance) between locations
##   N to 1  |
##   N to M  |
##-----------------------------------------------------------------------------------
## This script send multiple requests to an osrm local server
## in order to build a matrice of time/route_distance/euclidian_distance
## between a set of locations (centroid of city for example).
##
## The set of location must be provided in .csv (first line as headers) as:
## Lat_column,Long_column,Name_column
## lat,long,name_of_the_place1
## lat,long,name_of_the_place2
## .......
##
## Output is a shapefile containing the geometry of the fastest route,
## the time in seconds, route distance in meters and euclidian
## distance between the 2 locations in meters.

##-----------------------------------------------------------------------------------
## Usage :
##   try --help to get some help


import json
from osgeo import ogr
from osgeo import osr
from polyline.codec import PolylineCodec  # https://pypi.python.org/pypi/polyline
import urllib.request
import pyproj  # Python interface to PROJ.4 library
import csv
import sys
import os.path
import numpy as np


def query_osrm_to_shp(dict_coord, coord_liste_s, coord_liste_t, dstpath):
    """Fonction qui prend en entrée un dictionnaire de {coordonnées:noms} et les les listes de coordonées
    puis envoie les requetes au serveur OSRM et enregistre le résultat dans le fichier de sortie indiqué(.shp)"""

    # Création des matrices à remplir
    matrice_time = np.zeros([len(coord_liste_s), len(coord_liste_t)])
    matrice_distance = np.zeros([len(coord_liste_s), len(coord_liste_t)])
    matrice_euclidian_distance =np.zeros([len(coord_liste_s), len(coord_liste_t)])

    # Syst de coord. a adopter pour écrire le fichier shp
    spatialreference = osr.SpatialReference()
    spatialreference.SetWellKnownGeogCS('WGS84')

    # Syst de coord. pour le calcul de la distance à vol d'oiseau
    geod = pyproj.Geod(ellps='WGS84')

    # Définition du type du fichier de sortie..
    driver = ogr.GetDriverByName("ESRI Shapefile")
    # ..et vérification de son nom
    if '.shp' not in dstpath[len(dstpath) - 4:]:
        dstpath = dstpath + '.shp'

    try:
        dstfile = driver.CreateDataSource(dstpath)
        dstlayer = dstfile.CreateLayer("layer", spatialreference)
    except:
        print("Erreur lors de la création du fichier")
        sys.exit(0)

    # Ajout des champs à remplir
    fielddef = ogr.FieldDefn("ID", ogr.OFTInteger)
    fielddef.SetWidth(10)
    dstlayer.CreateField(fielddef)

    fielddef = ogr.FieldDefn("Total_time", ogr.OFTInteger)
    fielddef.SetWidth(14)
    dstlayer.CreateField(fielddef)

    fielddef = ogr.FieldDefn("Total_dist", ogr.OFTInteger)
    fielddef.SetWidth(14)
    dstlayer.CreateField(fielddef)

    fielddef = ogr.FieldDefn("Dist_eucl", ogr.OFTInteger)
    fielddef.SetWidth(14)
    dstlayer.CreateField(fielddef)

    fielddef = ogr.FieldDefn("Src_name", ogr.OFTString)
    fielddef.SetWidth(128)
    dstlayer.CreateField(fielddef)

    fielddef = ogr.FieldDefn("Tgt_name", ogr.OFTString)
    fielddef.SetWidth(128)
    dstlayer.CreateField(fielddef)

    print("\npyq-OSRM :\n\n {0} routes to calculate\n".format(len(coord_liste_s) * len(coord_liste_t)))
    testit = 0
    error = 0
    matrice_time_dic = {}
    for a, source in enumerate(coord_liste_s):
        src_name = str(dict_coord[source])
        matrice_time_dic[src_name] = {}
        for b, target in enumerate(coord_liste_t):
            tgt_name = str(dict_coord[target])
            # Préparation de la requete au serveur osrm, envoi et récupération de la réponse
            url_query = 'http://localhost:5000/viaroute?loc={0}&loc={1}&instructions=false&alt=false'.format(source, target)
            try:
                ajson = urllib.request.urlopen(url_query)
            except:
                print("\npyq-OSRM :\nErreur lors du passage de l'URL\n")
                sys.exit(0)

            # Lecture des résultats (bytes) en json
            json_entry = ajson.readall().decode('utf-8')
            parsed_json = json.loads(json_entry)
            
            # Calcul de la distance à vol d'oiseau entre l'origine et la destination du parcours
            angle1, angle2, distance_eucl = geod.inv(source[source.find(',') + 1:], source[:source.find(',')],
                                                     target[target.find(',') + 1:], target[:target.find(',')])
            distance_eucl = int(distance_eucl)


            if parsed_json['status'] is not 207:  # Verification qu'une route a bien été trouvée par OSRM

                # Récupération des infos intéressantes dont la géométrie au format encoded polyline algorythm
                epa_osrm = parsed_json['route_geometry']
                total_time_osrm = parsed_json['route_summary']['total_time']
                total_distance_osrm = parsed_json['route_summary']['total_distance']

                # Remplissage des matrices:
                matrice_time[a][b]=total_time_osrm
                matrice_distance[a][b]=total_distance_osrm
                matrice_euclidian_distance[a][b]=distance_eucl
                matrice_time_dic[src_name][tgt_name]=total_time_osrm
                
                # Décodage de la géométrie pour obtenir la liste des points composants la ligne
                epa_dec = PolylineCodec().decode(epa_osrm)
                fausse_liste = str(epa_dec)
                ma_ligne = ogr.Geometry(ogr.wkbLineString)

                # Liste des coordonées des points
                lat = []
                long = []
                valueliste = fausse_liste[1:len(fausse_liste) - 1].split(
                    ",")  # On saute le 1er et dernier caractère et on coupe aux vigules
                for i in valueliste:  # Récupération des coordonnées latitude longitude
                    if '(' in i:
                        lat.append(i[i.find('(') + 1:])
                    elif ')' in i:
                        long.append(i[i.find(' ') + 1:len(i) - 1])
                    else:
                        print("Error while getting node coordinates\n")

                if int((testit / (len(coord_liste_s) * len(coord_liste_t)) * 100)) % 5 == 0: print(
                    "Processing.... {0}%".format(int((testit / (len(coord_liste_s) * len(coord_liste_t)) * 100))))

                for j in range(len(lat)):  # Ajout des points à la future ligne...
                    ma_ligne.AddPoint(float(long[j]) / 10,
                                      float(lat[j]) / 10)  # ...sous la forme x y (longitude latitude)...

                feature = ogr.Feature(dstlayer.GetLayerDefn())  # ....

                # Ecriture de la geométrie et des champs
                feature.SetGeometry(ma_ligne)
                feature.SetField("ID", testit)
                feature.SetField("Total_time", total_time_osrm)
                feature.SetField("Total_dist", total_distance_osrm)
                feature.SetField("Dist_eucl", distance_eucl)
                feature.SetField("Src_name", src_name)
                feature.SetField("Tgt_name", tgt_name)
                dstlayer.CreateFeature(feature)
                testit += 1

            else:
                error += 1
                print(
                    "Err #{0}  : OSRM status 207 - No route found between {1} and {2}".format(error, src_name,
                                                                                              tgt_name))
                # Remplissage matrice en cas d'erreur:
                matrice_time[a][b]=-1
                matrice_distance[a][b]=-1
                matrice_euclidian_distance[a][b]=distance_eucl
                
    if error > 0 :
        print("\t{0} route(s) calculations failed".format(error))
    print("\t{0} lines created in a shapefile".format(testit))
    feature.Destroy()
    dstfile.Destroy()


def csv_to_dico_liste(file_path):
    my_dict = {}
    coord_liste = []
    with open(file_path, 'r') as file:
        reader = csv.reader(file)
        try:
            for row in reader:
                if reader.line_num is not 1:
                    concat = row[0] + ',' + row[1]
                    coord_liste.append(concat)
                    my_dict[concat] = row[2]
        except csv.Error as er:
            sys.exit('Erreur dans la lecture du fichier csv : file {}, line {}: {}'.format(file_path, reader.line_num, er))
    return my_dict, coord_liste


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description="pyq-osrm :\nPython script to query local osrm server and provide output as .shp")
    parser.add_argument(type=str, action='store', dest="csv_filename", default="", help=".csv file to open")
    parser.add_argument('-m', '--one-to-many', dest='one_t', action='store_true', default=False,
                        help="Calcul the fastest route between 1 source location and many destinations (default : Calcul fastest route between every locations provided in the dataset)")
    parser.add_argument('-t', '--many-to-one', dest='many_t', action='store_true', default=False,
                        help="Calcul the fastest route between many sources locations and 1 same destination (default : Calcul fastest route between every locations provided in the dataset)")
    parser.add_argument('-d', '--different', dest='destinations_csv', action='store', default="",
                        help="Different origins and destinations (put .csv file of destinations after this argument)")
    parser.add_argument('-o', '--output', dest='out_filename', action='store', default="",
                        help="Change output name file (default : same name as the csv)")
    args = parser.parse_args()
    
    if args.csv_filename:
        if '.csv' not in (str(args.csv_filename)[len(args.csv_filename)-4:]):
            print("Filename error")
            sys.exit(0)
    else:
        print("\n\nErreur lors de l'ouverture du fichier\n")
        sys.exit(0)        
    nom_fichier=args.csv_filename
    
    if os.path.isfile(nom_fichier) is False:
        print("\n\nErreur lors de l'ouverture du fichier\n")
        sys.exit(0)
        
    dico, liste_ord = csv_to_dico_liste(nom_fichier)
    coord_liste_t = []

    if args.out_filename: outfile=args.out_filename
    else: outfile=nom_fichier[:len(args.csv_filename)-4]
    
    if args.one_t:
        coord_liste_t.append(liste_ord[0])
        liste_ord, coord_liste_t = coord_liste_t, liste_ord
        print("\nMode 1-to-Many\n")
    elif args.many_t:
        coord_liste_t.append(liste_ord[0])
        print("\nMode Many-to-1\n")
    elif args.destinations_csv:
        dico_suite, liste_ord_d = csv_to_dico_liste(args.destinations_csv)
        dico.update(dico_suite)
        print("\nTest Mode N-to-M\n")
        print("{0}\n{1}\{2}\n{3}".format(dico,coord_liste_t, liste_ord_d, outfile))
        coord_liste_t = liste_ord_d
    else:
        coord_liste_t = liste_ord

    query_osrm_to_shp(dico, liste_ord, coord_liste_t, outfile)
