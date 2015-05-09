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
## pyq-osrm-tsp:
##
## Script querying local OSRM server to resolve TSP (traveller salesman problem).
## The input file must be a .csv (first line as headers) containing coordinates and
## name of each point as :
## lat, long, name
## The start and end point of the journey is the first one provided in the .csv file.
## The output is a shapefile containing the path passing through each point.

import json
from osgeo import ogr
from osgeo import osr
from polyline.codec import PolylineCodec  # https://pypi.python.org/pypi/polyline
import urllib.request
import csv
import sys
import os.path
import random
from simanneal import Annealer


class TravellingSalesmanProblem(Annealer):
    # From "perrygeo" : https://github.com/perrygeo/simanneal/blob/master/examples/salesman.py
    """Test annealer with a traveling salesman problem.
    """
    # pass extra data (the distance matrix) into the constructor
    def __init__(self, state, distance_matrix):
        self.distance_matrix = distance_matrix
        super(TravellingSalesmanProblem, self).__init__(state)  # important! 

    def move(self):
        """Swaps two cities in the route."""
        a = random.randint(0, len(self.state) - 1)
        b = random.randint(0, len(self.state) - 1)
        self.state[a], self.state[b] = self.state[b], self.state[a]

    def energy(self):
        """Calculates the length of the route."""
        e = 0
        for i in range(len(self.state)):
            e += self.distance_matrix[self.state[i - 1]][self.state[i]]
        return e


def query_osrm_matrice(dict_coord, coord_liste_s):
    matrice_time_dic = {}
    url_query = 'http://localhost:5000/table?'
    for i, coord in enumerate(coord_liste_s):
        matrice_time_dic[dict_coord[coord]] = {}
        if i == 0:
            to_add = 'loc={0}'.format(coord)
        else:
            to_add = '&loc={0}'.format(coord)
        url_query += to_add
    try:
        ajson = urllib.request.urlopen(url_query)
    except:
        print("\n\nErreur lors du passage de l'URL\n")
        sys.exit(0)
    json_entry = ajson.readall().decode('utf-8')
    parsed_json = json.loads(json_entry)
    table_distance = parsed_json['distance_table']
    for a, coord_h in enumerate(coord_liste_s):
        for b, coord_b in enumerate(coord_liste_s):
            matrice_time_dic[dict_coord[coord_h]][dict_coord[coord_b]] = table_distance[a][b]
    return matrice_time_dic


def query_osrm_suite_to_shp(dict_coord, coord_liste_suite, dstpath):
    # Syst de coord. a adopter pour écrire le fichier shp
    spatialreference = osr.SpatialReference()
    spatialreference.SetWellKnownGeogCS('WGS84')

    # Définition du type du fichier de sortie..
    driver = ogr.GetDriverByName("ESRI Shapefile")
    # ..et vérification de son nom
    if '.shp' not in dstpath[len(dstpath) - 4:]:
        dstpath += '.shp'

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

    fielddef = ogr.FieldDefn("Src_name", ogr.OFTString)
    fielddef.SetWidth(128)
    dstlayer.CreateField(fielddef)

    fielddef = ogr.FieldDefn("Tgt_name", ogr.OFTString)
    fielddef.SetWidth(128)
    dstlayer.CreateField(fielddef)

    print("\n\n Retrieving the geometry of {0} routes...\n".format(len(coord_liste_s)))
    testit = 0
    error = 0
    for a, target in enumerate(coord_liste_suite):
        if a is not 0:
            source = coord_liste_suite[a - 1]
            src_name = str(dict_coord[source])
            tgt_name = str(dict_coord[target])
            # Préparation de la requete au serveur osrm, envoi et récupération de la réponse
            url_query = 'http://localhost:5000/viaroute?loc={0}&loc={1}&instructions=false&alt=false'.format(source,
                                                                                                             target)
            try:
                ajson = urllib.request.urlopen(url_query)
            except:
                print("\npyq-OSRM :\nErreur lors du passage de l'URL\n")
                sys.exit(0)

            # Lecture des résultats (bytes) en json
            json_entry = ajson.readall().decode('utf-8')
            parsed_json = json.loads(json_entry)

            if parsed_json['status'] is not 207:  # Verification qu'une route a bien été trouvée par OSRM

                # Récupération des infos intéressantes dont la géométrie au format encoded polyline algorythm
                epa_osrm = parsed_json['route_geometry']
                total_time_osrm = parsed_json['route_summary']['total_time']
                total_distance_osrm = parsed_json['route_summary']['total_distance']

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

                for j in range(len(lat)):  # Ajout des points à la future ligne...
                    ma_ligne.AddPoint(float(long[j]) / 10,
                                      float(lat[j]) / 10)  # ...sous la forme x y (longitude latitude)...

                feature = ogr.Feature(dstlayer.GetLayerDefn())  # ....

                # Ecriture de la geométrie et des champs
                feature.SetGeometry(ma_ligne)
                feature.SetField("ID", testit)
                feature.SetField("Total_time", total_time_osrm)
                feature.SetField("Total_dist", total_distance_osrm)
                feature.SetField("Src_name", src_name)
                feature.SetField("Tgt_name", tgt_name)
                dstlayer.CreateFeature(feature)
                testit += 1

            else:
                error += 1
                print(
                    "Err #{0}  : OSRM status 207 - No route found between {1} and {2}".format(error, src_name,
                                                                                              tgt_name))
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
            sys.exit(
                'Erreur dans la lecture du fichier csv : file {}, line {}: {}'.format(file_path, reader.line_num, er))
    return my_dict, coord_liste


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description="pyq-osrm-tsp :\nScript querying local OSRM server to resolve TSP (traveller salesman problem)")
    parser.add_argument(type=str, action='store', dest="csv_filename", default="", help=".csv file to open")
    parser.add_argument('-o', '--output', dest='out_filename', action='store', default="",
                        help="Change output shapefile name (default : same name as the csv)")
    args = parser.parse_args()

    if args.csv_filename:
        if '.csv' not in (str(args.csv_filename)[len(args.csv_filename) - 4:]):
            print("Filename error")
            sys.exit(0)
    else:
        print("\n\nErreur lors de l'ouverture du fichier\n")
        sys.exit(0)
    nom_fichier = args.csv_filename

    if os.path.isfile(nom_fichier) is False:
        print("\n\nErreur lors de l'ouverture du fichier\n")
        sys.exit(0)

    dico, liste_ord = csv_to_dico_liste(nom_fichier)
    coord_liste_s = []
    coord_liste_t = []
    for i in liste_ord:
        coord_liste_t.append(i)

    coord_liste_s = coord_liste_t

    if args.out_filename:
        outfile = args.out_filename
    else:
        outfile = nom_fichier[:len(args.csv_filename) - 4]

    init_state = list(dico.values())
    random.shuffle(init_state)

    matrice_time = query_osrm_matrice(dico, coord_liste_s)

    tsp = TravellingSalesmanProblem(init_state, matrice_time)
    tsp.copy_strategy = "slice"
    tsp.steps = 100000
    tsp.Tmax = 37500
    state, time = tsp.anneal()
    tsp_ord_place = []

    while state[0] != dico[coord_liste_s[0]]:
        state = state[1:] + state[:1]  # In order to find the start point
    print("\n{0} minutes route\nOrdered list of destinations :".format(round(time / 600)))

    for pt in state:
        print("\t", pt)
        tsp_ord_place.append(pt)
    tsp_ord_place.append(dico[coord_liste_s[0]])

    inv_dico = {dico[k]: k for k in dico}
    liste = []
    for n in tsp_ord_place:
        liste.append(inv_dico[n])
    query_osrm_suite_to_shp(dico, liste, outfile)
