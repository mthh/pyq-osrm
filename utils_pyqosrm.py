# -*- coding: utf-8 -*-
"""
utils_pyqosrm
-------------
@author: mthh
"""
import asyncio
import aiohttp
import ogr
import osr
import sys
import os
from polyline.codec import PolylineCodec


class AsyncRoutesFetcher:
    def __init__(self, urls, concurrent_requests, dstpath, dico_loc):
        self.urls = urls
        self.concurrent_requests = concurrent_requests
        self.results = 0
        self.dico_loc = dico_loc
        spatialreference = osr.SpatialReference()
        spatialreference.SetWellKnownGeogCS('WGS84')
        # Définition du type du fichier de sortie..
        self.driver = ogr.GetDriverByName("ESRI Shapefile")
        fields = [
            ['ID', {'type': ogr.OFTInteger, 'width': 10}],
            ['Total_time', {'type': ogr.OFTInteger, 'width': 14}],
            ['Total_dist', {'type': ogr.OFTInteger, 'width': 14}],
            ['Src_name', {'type': ogr.OFTString, 'width': 80}],
            ['Tgt_name', {'type': ogr.OFTString, 'width': 80}]]

        try:
            if os.path.exists(dstpath):
                os.remove(dstpath)
            self.dstfile = self.driver.CreateDataSource(dstpath)
            self.dstlayer = self.dstfile.CreateLayer("layer", spatialreference)
        except Exception as err:
            print(err, "\nErreur lors de la création du fichier")
            sys.exit(0)

        for field_name, detail in fields:
            fielddef = ogr.FieldDefn(field_name, detail['type'])
            fielddef.SetWidth(detail['width'])
            self.dstlayer.CreateField(fielddef)

    def run(self, clean_older=False):
        semaphore = asyncio.Semaphore(self.concurrent_requests)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(asyncio.wait(
            [self.worker(u, semaphore) for u in self.urls]))
        self.dstfile.Destroy()
        return self.results

    @asyncio.coroutine
    def worker(self, url, semaphore):
        with (yield from semaphore):
            response = yield from aiohttp.request(
                'GET', url, connector=aiohttp.TCPConnector(
                    share_cookies=True, verify_ssl=False))
            try:
                body = yield from response.json()
            except:
                pass
            else:
                self.results += 1
                total_time_osrm = body['route_summary']['total_time']
                total_dist_osrm = body['route_summary']['total_distance']

                epa_dec = PolylineCodec().decode(body['route_geometry'])
                ma_ligne = ogr.Geometry(ogr.wkbLineString)
                line_add_pts = ma_ligne.AddPoint_2D

                origin = url[url.find('?loc=')+5:url.find('&')]
                dest = url[url.find('&loc=')+5:url.find('&ins')]

                for coord in epa_dec:
                    line_add_pts(coord[1]/10.0, coord[0]/10.0)

                feature = ogr.Feature(self.dstlayer.GetLayerDefn())
                feature.SetGeometry(ma_ligne)
                for f_name, f_value in zip(
                        ['ID', 'Total_time', 'Total_dist',
                         'Src_name', 'Tgt_name'],
                        [self.results, total_time_osrm, total_dist_osrm,
                         self.dico_loc[origin], self.dico_loc[dest]]):
                    feature.SetField(f_name, f_value)
                self.dstlayer.CreateFeature(feature)
                feature.Destroy()

