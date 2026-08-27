# Complementary data for the Lhende barrier lake, checked 27 Aug 2026

Sentinel-1 answers presence and extent. It does not answer volume, inflow, or
uncertainty. This is what else was checked and what came of it.

## Used

**Sentinel-2 L2A** (Planetary Computer, no key). Optical was not blind on the
date that mattered: 24 Aug was 75.6% clear over the source zone and 51.7% over
the blockage reach, and by 27 Aug the same zone is down to 11% clear. The
classifier flags 6.9% of the source zone as water on 24 Aug against 0.15% on
12 Aug, which does not survive a spectral check: median near infrared 0.116 and
shortwave 0.117, where liquid water sits below 0.05 in the near infrared. Not
one pixel on either date passes 0.10 in both bands. Cloud shadow, in a zone that
was 24% cloud. Independent confirmation of the radar null.
See `nepal_optical_check.py` and `nepal_optical_water.py`.

**Copernicus GLO-30, NASADEM, ALOS World 3D-30m** (Planetary Computer). Run the
same fixed impoundment footprint through all three. On the valley floor, which
is the population that matters for a volume integral, they agree to a median of
about 1 m with a standard deviation of 6 to 8 m, against 18 to 22 m across all
terrain where steep slopes dominate the scatter. Volume spread across the three
is **3 to 4%**. The DEM is not the dominant error term, which was not the
expected answer. Stage estimation and the radar water outline are.
See `nepal_barrier_context_2026.py dem`.

**Open-Meteo precipitation** (no key, non-commercial terms). Catchment-mean
rainfall over 16 sample points. Two results worth having. The days before the
collapse were nearly dry, 0.3 to 2.3 mm/day from 20 to 25 Aug, which supports an
avalanche trigger rather than a rainfall one and independently supports the null,
since there was no water available to fill an impoundment quickly. And 29 to 31
Aug carries 11.1, 7.5 and 6.2 mm, arriving while the barrier lake fills. For
China's 3 Mm3 three-day inflow to come from rainfall alone needs a catchment of
266 to 479 km2 depending on runoff coefficient, which is large but plausible for
the Chhochen and Purepu catchments combined, and melt contributes on top. Their
figure is consistent.
See `nepal_barrier_context_2026.py inflow`.

## Checked and rejected

**GPM IMERG** on Planetary Computer stops at 31 May 2021. Useless for a live
event. The NASA GES DISC feed is current but needs an Earthdata login. Open-Meteo
was the practical substitute and also carries a forecast, which IMERG does not.

**ICESat-2** (ATL13 inland water, ATL03 photons, via NASA CMR). No usable recent
track over this catchment. The 91-day repeat with sparse ground tracks makes a
hit on a specific small lake in a specific week unlikely, and that is what
happened. Worth re-querying if the lake persists for months.

## Worth getting, not yet pulled

**SWOT** (`SWOT_L2_HR_Raster_100m_D`, PO.DAAC). This is the mission built for
the exact question, and it does cover the catchment. UTM45R granules land in
pairs: 29 and 31 July, 8 and 10 August, 19 and 21 August, so the next pair falls
around 30 August to 1 September, inside the critical window. It measures water
surface elevation directly, which would replace the DEM shoreline proxy with a
real measurement. Two caveats. Download needs a free Earthdata login. And SWOT
is specified for water bodies wider than roughly 250 m, so a confined gorge
impoundment sits at the edge of what it can resolve.

**Planet Crisis Response** at
`https://data.source.coop/planet/disasterdata/nepal-flash-flood-2026-08-26`,
anonymous S3 listing, STAC catalog at `catalog.json`. 16 scenes: 5 PlanetScope
pre-event from 27 May, 9 PlanetScope from the morning of 26 August, and 2 SkySat
at 0.8 m from 27 August over Rasuwagadhi and Syabrubesi. Two limits to note
before planning around it. Coverage runs 84.894 to 85.648 E and 27.795 to 28.659
N, which is the downstream damage corridor and probably stops short of the
barrier lake. And cloud is heavy: 62 to 93% on the post-event PlanetScope, 50% on
the SkySat. Good for deposit and damage mapping downstream, thin for the lake.
Licensed CC-BY-NC-4.0, so attribution is required and commercial use is not
permitted. That rules it out of any client deliverable.

## Not yet touched

**Seismic** (IRIS, GEOFON, open waveforms). The 26 Aug collapse registered 5.2
and the note on this event concluded that seismic detection, not orbit, is the
instrument with a usable warning window for this hazard class. It would give an
exact origin time, an avalanche volume by force-history inversion, and near real
time detection of a second detachment. It is free and it is the obvious gap.
