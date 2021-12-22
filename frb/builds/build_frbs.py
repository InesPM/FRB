""" Top-level module to build or re-build the JSON files for FRBs """

from pkg_resources import resource_filename
import os
import sys
import warnings

from IPython import embed

import numpy as np
import requests

import pandas

from astropy.coordinates import SkyCoord
from astropy import units
from astropy.table import Table
from astropy.coordinates import match_coordinates_sky

from frb.frb import FRB, load_base_tbl
from frb.galaxies import frbgalaxy, defs, offsets
from frb.galaxies import photom as frbphotom
from frb.surveys import survey_utils
from frb import utils
import pandas


            

def run(frb_input:pandas.core.series.Series, 
        lit_refs:str=None,
        override:bool=False, out_path:str=None,
        outfile:str=None):
    """Main method for generating a Host JSON file

    Args:
        frb_input (pandas.core.series.Series): Row of the CVS file
            providing the frb items
        lit_refs (str, optional): File of literature references. Defaults to None.
        override (bool, optional): Attempt to over-ride errors. 
            Mainly for time-outs of public data. Defaults to False.
        outfile (str, optional): Over-ride default outfile [not recommended; mainly for testing]
        out_path (str, optional): Over-ride default outfile [not recommended; mainly for testing]


    Raises:
        e: [description]
        ValueError: [description]
    """

    frbname = utils.parse_frb_name(frb_input.FRB)

    print("--------------------------------------")
    print(f"Building FRB JSON file for {frbname}")

    # Instantiate
    ifrb = FRB(frb_input.name, 
              (frb_input.ra, frb_input.dec),
              frb_input.DM*units.pc/units.cm**3,
              z_frb=frb_input.z if np.isfinite(frb_input.z) else None, 
              repeater=frb_input.repeate)

    # Add DM_ISM from NE2001
    ifrb.set_DMISM()


    '''
    # SAVING FOR LATER
    lit_tbls = pandas.read_csv(lit_refs)

    for kk in range(len(lit_tbls)):
        lit_entry = lit_tbls.iloc[kk]
        if 'photom' not in lit_entry.Table:
            continue
        # Load table
        sub_tbl = read_lit_table(lit_entry, coord=Host.coord)
        if sub_tbl is not None:
            # Add Ref
            for key in sub_tbl.keys():
                if 'err' in key:
                    newkey = key.replace('err', 'ref')
                    sub_tbl[newkey] = lit_entry.Reference
            # Merge?
            if merge_tbl is not None:
                for key in sub_tbl.keys():
                    if key == 'Name':
                        continue
                    if key in merge_tbl.keys():
                        if sub_tbl[key] == fill_value:
                            continue
                        else:
                            merge_tbl[key] = sub_tbl[key]
                    else:
                        if sub_tbl[key] != fill_value:
                            merge_tbl[key] = sub_tbl[key]
                #merge_tbl = frbphotom.merge_photom_tables(sub_tbl, merge_tbl)
            else:
                merge_tbl = sub_tbl
                merge_tbl['Name'] = file_root

    # Finish
    if merge_tbl is not None:
        # Dust correct
        EBV = nebular.get_ebv(gal_coord)['meanValue']
        frbphotom.correct_photom_table(merge_tbl, EBV, Host.name)
        # Parse
        Host.parse_photom(merge_tbl, EBV=EBV)
    else:
        print(f"No photometry for {file_root}")
    '''

    # Vet all
    assert ifrb.vet_all()

    # Write
    if out_path is None:
        out_path = os.path.join(resource_filename('frb', 'data'), 'FRBs')
    ifrb.write_to_json(path=out_path)


def main(frbs:list, options:str=None, hosts_file:str=None, lit_refs:str=None,
         override:bool=False, outfile:str=None, out_path:str=None):
    """ Driver of the analysis

    Args:
        frbs (list): [description]
        options (str, optional): [description]. Defaults to None.
        hosts_file (str, optional): [description]. Defaults to None.
        lit_refs (str, optional): [description]. Defaults to None.
        override (bool, optional): [description]. Defaults to False.
        outfile (str, optional): [description]. Defaults to None.
            Here for testing
        out_path (str, optional): [description]. Defaults to None.
            Here for testing
    """
    # Options
    build_cigale, build_ppxf = False, False
    if options is not None:
        if 'cigale' in options:
            build_cigale = True
        if 'ppxf' in options:
            build_ppxf = True

    # Read public FRB table
    frb_tbl = load_base_tbl(hosts_file=hosts_file)

    # Loop me
    if frbs == 'all':
        embed(header='Generate code to (i) load up the FRB table; (ii) generate a list')
    elif isinstance(frbs, list):
        pass

    for frb in frbs:
        frb_name = utils.parse_frb_name(frb, prefix='')
        mt_idx = frb_tbl.FRB == frb_name
        idx = np.where(mt_idx)[0].tolist()
        # Do it!
        for ii in idx:
            run(frb_tbl.iloc[ii], 
                lit_refs=lit_refs, override=override,
                outfile=outfile, out_path=out_path)

    # 
    print("All done!")

# Run em all
#  frb_build FRBs --frb 20181112,20190711,20200906,20121102,20190102,20190714,20201124,20171020,20190523,20191001,20180301,20190608,20191228,20180916,20190611,20180924,20190614,20200430