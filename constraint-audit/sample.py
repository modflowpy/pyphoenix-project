"""Pass 2 step 3 + pass 3 of constraint-audit-plan.md: hand-labelled sample of MF6 checks and
mf6io prose rules. Writes mf6-sample.csv and prints tallies.

Usage: python sample.py <out dir>

Columns
  site      MF6 file:line, or doc:<file> for prose-only rules
  kind      K1..K10, or L (lens domain: where a layout's partial lens is defined)
  level     layout | logical | runtime
  arity     field | row | table | component | multi | sim
  cd        config | data | cfg-data (relates configuration to data)
  trigger   uncond | opt:<name>(<label>) | dim | binding | presence:<component>
  dfn       yes | partly | no   (expressible in dev3 DFN keys today)
  ddl       construct a DDL-style logical spec would use, or none:<why>
  sev       e | w
  when      load | ar | rp | ad  (MF6 phase where it is checked)
MF6 at 8aad7bc4a5.
"""

import collections
import csv
import os
import sys

S = []


def s(site, msg, kind, level, arity, cd, trigger, dfn, ddl, sev="e", when="load"):
    S.append(dict(site=site, msg=msg, kind=kind, level=level, arity=arity, cd=cd, trigger=trigger,
                  dfn=dfn, ddl=ddl, sev=sev, when=when))


# ---- generic IDM / framework -------------------------------------------------------------
s("LoadMf6File.f90:419", "record with keyword not properly formed", "K1", "layout", "row", "data", "uncond", "yes", "none:syntax")
s("StructArray.f90:1237", "unrecognized keystring keyword in PERIOD", "K1", "layout", "row", "data", "uncond", "yes", "none:syntax")
s("SourceCommon.f90:470", "multiple FILEIN for one tag", "K1", "layout", "field", "config", "uncond", "no", "none:syntax")
s("SourceCommon.f90:499", "input name exceeds max length", "K2", "logical", "field", "data", "uncond", "no", "CHECK(length)")
s("StructArray.f90:1015", "CELLID must be integer or NONE", "K1", "layout", "field", "data", "uncond", "partly", "none:syntax")
s("IdmMf6File.f90:249", "period numbers not increasing", "K9", "layout", "component", "data", "uncond", "partly", "none:block order")
s("StructArray.f90:1114", "line count exceeds input dimension", "K3", "logical", "table", "cfg-data", "dim", "yes", "CHECK(count(*)<=dim)")
s("StructArray.f90:1198", "keystring rows exceed MAXBOUND", "K3", "logical", "table", "cfg-data", "dim", "yes", "CHECK(count(*)<=dim)")
s("Mf6FileGridArray.f90:261", "defined cells exceed MAXBOUND", "K3", "logical", "table", "cfg-data", "dim", "partly", "CHECK(count(*)<=dim)")
s("LoadContext.f90:719", "dimension does not match PACKAGEDATA row count", "K3", "logical", "table", "cfg-data", "dim", "partly", "CHECK(count(*)=dim)")
s("Mf6FileKeystring.f90:381", "feature number on row out of 1..n", "K7", "logical", "row", "data", "dim", "yes", "FK")
s("SourceCommon.f90:291", "required dimension NLAY not found", "K4", "logical", "field", "config", "uncond", "yes", "NOT NULL")
s("ModelPackageInputs.f90:329", "DIS package not specified for model", "K8", "logical", "multi", "config", "uncond", "no", "assertion:exists")
s("ModelPackageInputs.f90:434", "multiple instances of base package type", "K8", "logical", "multi", "config", "uncond", "yes", "UNIQUE(model,ftype)")
s("ModelPackageInputs.f90:246", "models block model type not valid", "K2", "logical", "field", "config", "uncond", "partly", "CHECK(in)")
s("IdmLoad.f90:362", "exchange has unrecognized model names", "K7", "logical", "multi", "config", "uncond", "yes", "FK")
s("NCArrayReader.f90:440", "layered netcdf read not supported for DIS int2d", "L", "layout", "field", "data", "opt:netcdf(layout)", "no", "none:encoding domain")
s("StructArray.f90:1334", "binary list input not supported for text columns", "L", "layout", "table", "data", "opt:binary(layout)", "no", "none:encoding domain")
s("SourceLoad.F90:398", "NetCDF keyword but no NetCDF libraries", "-", "runtime", "sim", "config", "opt:netcdf(layout)", "no", "none:build")

# ---- simulation / solutions / timing -------------------------------------------------------
s("SimulationCreate.f90:867", "model names must be unique", "K6", "logical", "table", "config", "uncond", "yes", "PK")
s("SimulationCreate.f90:859", "model name cannot have spaces", "K2", "logical", "field", "config", "uncond", "no", "CHECK(pattern)")
s("SimulationCreate.f90:784", "model not assigned to a solution", "K8", "logical", "multi", "config", "uncond", "no", "assertion:total")
s("SimulationCreate.f90:688", "explicit model cannot be in IMS", "K8", "logical", "multi", "config", "binding", "no", "assertion:type match")
s("SimulationCreate.f90:539", "MXITER>1 with one solution in group", "K5", "logical", "multi", "config", "binding", "no", "assertion")
s("SimulationCreate.f90:636", "solution group blocks not consecutive", "K1", "layout", "component", "config", "uncond", "no", "none:block order")
s("SimulationCreate.f90:191", "TDIS6 unset", "K4", "logical", "field", "config", "uncond", "yes", "NOT NULL")
s("tdis.f90:632", "NSTP less than one", "K2", "logical", "field", "data", "uncond", "no", "CHECK")
s("tdis.f90:652", "PERLEN cannot be negative", "K2", "logical", "field", "data", "uncond", "no", "CHECK")
s("tdis.f90:671", "time step length too small", "K10", "runtime", "row", "data", "uncond", "no", "none:numerics", when="ar")
s("ats.f90:428", "IPERATS must be > 0", "K9", "logical", "field", "data", "uncond", "no", "FK(period)")
s("ats.f90:434", "IPERATS greater than NPER", "K9", "logical", "field", "data", "dim", "no", "FK(period)", sev="w")
s("ats.f90:466", "DTMIN must be < DTMAX", "K2", "logical", "row", "data", "uncond", "no", "CHECK(row)")
s("ImsLinear.f90:199", "RCLOSE must be > 0", "K2", "logical", "field", "config", "uncond", "no", "CHECK")
s("ImsLinear.f90:185", "ISCL must be <= 2", "K2", "logical", "field", "config", "uncond", "no", "CHECK(in)")

# ---- GWF discretization ------------------------------------------------------------------
s("Dis.f90:264", "NLAY not specified or <=0", "K2", "logical", "field", "config", "uncond", "partly", "CHECK(>0)")
s("Dis.f90:418", "no active nodes (IDOMAIN)", "K10", "logical", "table", "data", "uncond", "no", "assertion:exists")
s("Dis.f90:800", "layer out of 1..nlay", "K7", "logical", "field", "data", "dim", "partly", "FK(grid)")
s("Dis.f90:1620", "MAXBOUND too small (array->list)", "K3", "logical", "table", "cfg-data", "dim", "partly", "CHECK(count(*)<=dim)", when="rp")
s("Disu.f90:413", "first connection must be self", "K1", "layout", "row", "data", "uncond", "no", "none:CSR encoding", when="ar")
s("Disu.f90:422", "invalid connection in JA", "K7", "logical", "row", "data", "dim", "no", "FK(node)", when="ar")
s("Disu.f90:438", "invalid IDOMAIN value", "K2", "logical", "field", "data", "uncond", "no", "CHECK(in)", when="ar")
s("Disu.f90:479", "top above bottom of overlying cell (offset tol)", "K10", "logical", "multi", "data", "opt:vertical_offset_tolerance(output)", "no", "assertion:join", when="ar")
s("Disu.f90:1135", "ICELL2D input sequence violation", "K1", "layout", "table", "data", "uncond", "no", "none:row order")
s("Disu.f90:1460", "unit vectors need VERTEX data", "K4", "logical", "component", "data", "presence:vertices", "no", "assertion:exists", when="ar")
s("doc:gwf/disv.tex", "cell vertices in clockwise order", "K10", "logical", "row", "data", "uncond", "no", "none:geometry predicate")
s("Disu(npf.f90:391)", "ANGLDEGX inconsistent across faces", "K10", "logical", "multi", "data", "uncond", "no", "assertion:join", when="ar")

# ---- NPF / STO / IC / TVK ------------------------------------------------------------------
s("gwf-npf.f90:280", "XT3D cannot be used with GNC", "K8", "logical", "multi", "config", "presence:gnc", "no", "assertion:exclusion", when="ar")
s("gwf-npf.f90:1715", "NEWTON cannot be used with PERCHED", "K5", "logical", "multi", "config", "opt:newton(logical)", "no", "CHECK(cross-table)")
s("gwf-npf.f90:1742", "ALTERNATIVE_CELL_AVERAGING not with XT3D", "K5", "logical", "component", "config", "opt:xt3d(logical)", "no", "CHECK(row)")
s("gwf-npf.f90:1733", "HIGHEST_CELL_SATURATION ignored without NEWTON", "K5", "logical", "multi", "config", "opt:newton(logical)", "no", "CHECK(cross-table)", sev="w")
s("gwf-npf.f90:1862", "K not found in GRIDDATA", "K4", "logical", "field", "data", "uncond", "yes", "NOT NULL")
s("gwf-npf.f90:1874", "K22OVERK specified but K22 not", "K4", "layout", "component", "cfg-data", "opt:k22overk(layout)", "no", "none:layout flag needs data")
s("gwf-npf.f90:1942", "K <= 0 for cell", "K2", "logical", "field", "data", "uncond", "no", "CHECK(>0)", when="ar")
s("gwf-npf.f90:1981", "K22 given but no ANGLDEGX in DIS", "K4", "logical", "multi", "data", "presence:k22", "no", "assertion:cross-component", when="ar")
s("gwf-npf.f90:2032", "ANGLE2 requires ANGLE1", "K4", "logical", "component", "data", "presence:angle1", "no", "CHECK(row: a2 -> a1)", when="ar")
s("gwf-npf.f90:2195", "negative cell thickness (top-bot)", "K10", "logical", "multi", "data", "uncond", "no", "assertion:join", when="ar")
s("gwf-npf.f90:2466", "CHD cell went dry", "-", "runtime", "cell", "data", "uncond", "no", "none:state", when="ad")
s("gwf-sto.f90:1160", "SS < 0", "K2", "logical", "field", "data", "uncond", "no", "CHECK(>=0)", when="ar")
s("gwf-sto.f90:281", "zero DELT with STO", "K10", "logical", "multi", "data", "presence:sto", "no", "assertion:cross-component", when="ad")
s("gwf-ic.f90:159", "STRT not found", "K4", "logical", "field", "data", "uncond", "yes", "NOT NULL")
s("gwf-tvk.f90:126", "CELLID not in active domain", "K7", "logical", "row", "data", "binding", "partly", "FK(active cell)", when="rp")
s("gwf-tvk.f90:236", "changed K <= 0", "K2", "logical", "field", "data", "uncond", "no", "CHECK(>0)", when="ad")

# ---- stress packages (generic + CHD/WEL/EVT) -------------------------------------------------
s("BoundaryPackage.f90:1406", "MAXBOUND must be > 0", "K2", "logical", "field", "config", "uncond", "no", "CHECK(>0)")
s("BoundaryPackage.f90:1286", "multiple OBS6 entries", "K8", "logical", "component", "config", "uncond", "no", "UNIQUE")
s("BoundaryPackage.f90:1252", "TAS6 not for this discretization", "L", "layout", "multi", "config", "binding", "no", "none:encoding domain")
s("BoundaryPackage.f90:1331", "AUXMULTNAME given but no AUX", "K7", "logical", "component", "config", "opt:auxmultname(logical/schema)", "partly", "FK(options.auxiliary)")
s("BoundaryPackage.f90:338", "expecting BEGIN PERIOD", "K1", "layout", "component", "data", "uncond", "yes", "none:syntax", when="rp")
s("gwf-chd.f90:154", "cell already a constant head", "K6", "logical", "multi", "data", "uncond", "no", "UNIQUE(cell) across packages", when="rp")
s("gwf-wel.f90:231", "FLOW_REDUCTION_LENGTH without AUTO_FLOW_REDUCE ignored", "K5", "layout", "component", "config", "opt:flow_reduction_length(layout)", "no", "CHECK(row)", sev="w")
s("gwf-wel.f90:280", "AUTO_FLOW_REDUCE_AUXNAME not in AUX", "K7", "logical", "component", "config", "opt:auxiliary(logical)", "no", "FK(options.auxiliary)")
s("gwf-evt.f90:202", "READASARRAYS not with SURF_RATE_SPECIFIED", "L", "layout", "component", "config", "opt:readasarrays(layout)", "no", "none:encoding domain")
s("gwf-evt.f90:291", "NSEG>1 not with READASARRAYS", "L", "layout", "component", "config", "opt:readasarrays(layout)", "no", "none:encoding domain")
s("gwf-evt.f90:383", "PXDP must be in (0,1)", "K2", "logical", "field", "data", "uncond", "no", "CHECK", when="rp")
s("gwf-evt.f90:395", "PXDP not monotonically increasing", "K2", "logical", "row", "data", "dim", "no", "CHECK(row, ordered columns)", when="rp")
s("doc:gwf/evt.tex", "list input required for DISU", "L", "layout", "multi", "config", "binding", "no", "none:encoding domain")

# ---- advanced packages: SFR / LAK / MAW / UZF / CSUB --------------------------------------------
s("gwf-sfr.f90:909", "STORAGE_WEIGHT in [0.5,1]", "K2", "logical", "field", "config", "uncond", "no", "CHECK")
s("gwf-sfr.f90:1730", "ATS_COURANT requires STORAGE", "K5", "logical", "component", "config", "opt:ats_courant(logical)", "no", "CHECK(row)")
s("gwf-sfr.f90:1742", "ATS_COURANT but no ATS in TDIS", "K8", "logical", "multi", "config", "presence:ats", "no", "assertion:exists", sev="w")
s("gwf-sfr.f90:4170", "UNIT_CONVERSION with LENGTH/TIME_CONVERSION", "K5", "layout", "component", "config", "opt:unit_conversion(layout)", "no", "CHECK(row)")
s("gwf-sfr.f90:1346", "connections given but NCON differs", "K3", "logical", "table", "data", "dim", "no", "CHECK(count per key = column)")
s("gwf-sfr.f90:1365", "reach number exceeds NREACHES", "K7", "logical", "row", "data", "dim", "yes", "FK")
s("gwf-sfr.f90:1513", "DIVERSIONS block without diversions", "K4", "logical", "component", "data", "dim", "no", "assertion")
s("gwf-sfr.f90:1593", "reach diversion specified more than once", "K6", "logical", "table", "data", "uncond", "partly", "PK")
s("gwf-sfr.f90:1574", "invalid cprior type", "K2", "logical", "field", "data", "uncond", "no", "CHECK(in)")
s("gwf-sfr.f90:1908", "FRACTION divflow outside [0,1]", "K2", "logical", "row", "data", "uncond", "no", "CHECK(row: cprior -> range)", when="rp")
s("gwf-sfr.f90:4269", "reach length must be > 0", "K2", "logical", "field", "data", "uncond", "no", "CHECK")
s("gwf-sfr.f90:4434", "connection not reciprocal", "K10", "logical", "table", "data", "uncond", "no", "assertion:self-join", when="ar")
s("gwf-sfr.f90:4961", "upstream fractions do not sum to one", "K10", "logical", "table", "data", "uncond", "no", "assertion:aggregate", when="ar")
s("gwf-sfr.f90:1442", "reach graph has a cycle (warning)", "K10", "logical", "table", "data", "uncond", "no", "none:recursive", sev="w", when="ar")
s("gwf-sfr.f90:1658", "initial stage below reach top", "K10", "logical", "row", "data", "uncond", "no", "CHECK(row)", when="ar")
s("gwf-sfr.f90:3369", "obs boundname must be unique", "K6", "logical", "multi", "data", "opt:boundnames(logical)", "no", "UNIQUE(conditional)", when="rp")
s("gwf-lak.f90:792", "IMPLICIT requires a GWF connection per lake", "K5", "logical", "table", "data", "opt:implicit(logical)", "no", "assertion:aggregate")
s("gwf-lak.f90:1092", "telev >= belev for horizontal connection", "K10", "logical", "row", "data", "opt:ctype", "no", "CHECK(row)")
s("gwf-lak.f90:1097", "belev >= cell bottom", "K10", "logical", "multi", "data", "uncond", "no", "assertion:join", when="ar")
s("gwf-lak.f90:1122", "lake connection specified more than once", "K6", "logical", "table", "data", "uncond", "yes", "PK")
s("gwf-lak.f90:1171", "NTABLES > 0 but no TABLES block", "K4", "logical", "component", "cfg-data", "dim", "no", "CHECK(count(*)=dim)")
s("gwf-lak.f90:1387", "table stage not increasing", "K2", "logical", "table", "data", "uncond", "no", "none:ordered rows")
s("gwf-lak.f90:3116", "DEV_FORCE_LEGACY and DEV_FORCE_LEGACY_LAKE", "K5", "logical", "component", "config", "opt:dev(logical)", "no", "CHECK(row)")
s("gwf-lak.f90:6455", "IMPLICIT not with BUY", "K8", "logical", "multi", "config", "presence:buy", "no", "assertion:exclusion")
s("gwf-maw.f90:1234", "one connection per cell unless MEAN", "K6", "logical", "table", "data", "opt:condeqn", "no", "UNIQUE(conditional)")
s("gwf-maw.f90:1311", "ANGLEDATA block without NON_VERTICAL_WELLS", "K4", "logical", "component", "data", "opt:non_vertical_wells(logical)", "no", "conditional table")
s("gwf-maw.f90:1193", "screen radius <= well radius", "K10", "logical", "multi", "data", "uncond", "no", "assertion:join")
s("gwf-maw.f90:972", "CONDEQN deprecated spelling", "K1", "layout", "field", "data", "uncond", "no", "none:alias", sev="w")
s("gwf-uzf.f90:1823", "THTS must be > THTR", "K2", "logical", "row", "data", "uncond", "no", "CHECK(row)")
s("gwf-uzf.f90:1799", "SURFDEP > cell thickness", "K10", "logical", "multi", "data", "uncond", "no", "assertion:join")
s("gwf-uzf.f90:2063", "total UZF area exceeds cell area", "K10", "logical", "multi", "data", "uncond", "no", "assertion:aggregate", when="ar")
s("gwf-csub.f90:455", "STO SS must be zero when CSUB used", "K8", "logical", "multi", "data", "presence:csub", "no", "assertion:cross-component", when="ar")
s("gwf-csub.f90:1610", "NDELAYCELLS odd for effective stress", "K5", "logical", "component", "config", "opt:head_based(mixed)", "no", "CHECK(row)")
s("gwf-csub.f90:1474", "BOUNDNAME required for entry (BOUNDNAMES on)", "K4", "logical", "row", "data", "opt:boundnames(logical)", "yes", "NOT NULL(conditional)")
s("gwf-csub.f90:2511", "only first/last period steady with interbeds", "K9", "logical", "multi", "data", "presence:csub", "no", "assertion:cross-component", when="rp")
s("gwf-csub.f90:3928", "small/negative effective stress", "-", "runtime", "cell", "data", "uncond", "no", "none:state", when="ad")

# ---- MVR / exchanges ---------------------------------------------------------------------------
s("gwf-mvr.f90:789", "MODELNAMES only for exchange MVR", "K5", "layout", "component", "config", "binding", "partly", "none:fixed by binding")
s("gwf-mvr.f90:798", "MODELNAMES required for exchange MVR", "K5", "layout", "component", "config", "binding", "partly", "none:fixed by binding")
s("gwf-mvr.f90:373", "provider not listed in PACKAGES", "K7", "logical", "row", "data", "uncond", "yes", "FK")
s("gwf-mvr.f90:917", "package listed twice in PACKAGES", "K6", "logical", "table", "data", "uncond", "yes", "PK")
s("gwf-mvr.f90:935", "number of packages != MAXPACKAGES", "K3", "logical", "table", "cfg-data", "dim", "partly", "CHECK(count(*)=dim)")
s("gwf-mvr.f90:963", "package lacks MOVER option", "K7", "logical", "multi", "cfg-data", "opt:mover(logical/binding)", "partly", "FK(conditional role)")
s("Mover.f90:112", "provider and receiver are the same", "K10", "logical", "row", "data", "uncond", "no", "CHECK(row)", when="rp")
s("Mover.f90:154", "provider id out of package size", "K7", "logical", "multi", "data", "binding", "partly", "FK(role)", when="rp")
s("exg-gwfgwf.f90:187", "first model not of correct type", "K7", "logical", "multi", "config", "uncond", "partly", "FK(typed)")
s("exg-gwfgwf.f90:220", "models in different solutions", "K8", "logical", "multi", "config", "binding", "no", "assertion:join")
s("exg-gwfgwf.f90:294", "XT3D requires ANGLDEGX aux", "K4", "logical", "multi", "config", "presence:xt3d", "no", "assertion:cross-component")
s("exg-gwfgwf.f90:1361", "number of exchanges != number of GNCs", "K3", "logical", "multi", "data", "binding", "no", "assertion:cross-component")
s("exg-gwfgwf.f90:1353", "explicit GNC with Newton exchange", "K5", "logical", "multi", "config", "opt:newton(logical)", "no", "assertion:cross-component")
s("exg-gwfgwt.f90:165", "GWF and GWT in different solutions", "K8", "logical", "multi", "config", "binding", "no", "assertion:join")
s("exg-gwfgwt.f90:231", "GWF and GWT discretizations differ", "K8", "logical", "multi", "data", "binding", "no", "assertion:equal grids", when="ar")
s("exg-gwfgwt.f90:447", "GWT-GWT exchange without matching GWF-GWF", "K8", "logical", "multi", "data", "binding", "no", "assertion:equal tables")
s("gwf-buy.f90:264", "BUY species without concentration", "K7", "logical", "multi", "config", "binding", "no", "FK(model)", when="ar")

# ---- GWT/GWE ---------------------------------------------------------------------------------
s("tsp-fmi.f90:123", "GWF MVR active but no MVT", "K8", "logical", "multi", "config", "presence:mvr", "no", "assertion:co-occurrence")
s("tsp-fmi.f90:676", "budget file lacks specific discharge", "K8", "logical", "multi", "config", "presence:fmi file", "no", "none:external file content", when="ar")
s("tsp-ssm.f90:160", "no flows need SSM terms", "K8", "logical", "multi", "config", "binding", "no", "assertion:exists", when="ar")
s("tsp-ssm.f90:810", "flow package cannot be found", "K7", "logical", "multi", "data", "binding", "partly", "FK(rule flow_model)", when="ar")
s("tsp-ssm.f90:820", "package more than once in SOURCES", "K6", "logical", "table", "data", "uncond", "no", "PK")
s("tsp-ssm.f90:995", "auxiliary name cannot be found", "K7", "logical", "multi", "data", "binding", "no", "FK(other component's column)", when="ar")
s("TspSpc.f90:347", "SPC MAXBOUND < flow package bounds", "K3", "logical", "multi", "cfg-data", "binding", "no", "assertion:cross-component", when="rp")
s("TspSpc.f90:360", "array RCH needs array SPC", "K7", "logical", "multi", "config", "binding", "partly", "FK(key kind)")
s("gwt-mst.f90:1285", "sorption active but no BULK_DENSITY", "K4", "logical", "component", "data", "opt:sorption(logical/schema)", "no", "NOT NULL(conditional)")
s("gwt-mst.f90:1306", "BULK_DENSITY given without sorption", "K4", "logical", "component", "data", "opt:sorption(logical/schema)", "no", "NULL(conditional)", sev="w")
s("gwe-ctp.f90:160", "cell already constant temperature", "K6", "logical", "multi", "data", "uncond", "no", "UNIQUE(cell) across packages", when="rp")
s("doc:gwt/sft.tex", "SFT name defaults to SFR name", "K7", "logical", "multi", "config", "binding", "partly", "FK(default from name)")
s("doc:gwt/lkt.tex", "LKT needs corresponding LAK", "K8", "logical", "multi", "config", "binding", "no", "assertion:co-occurrence")

# ---- PRT ---------------------------------------------------------------------------------------
s("prt-prp.f90:928", "DRY_TRACKING_METHOD enum", "K2", "logical", "field", "config", "uncond", "partly", "CHECK(in)")
s("prt-prp.f90:937", "EXIT_SOLVE_TOLERANCE positive", "K2", "logical", "field", "config", "uncond", "no", "CHECK")
s("prt-prp.f90:585", "release point not in cell", "K10", "logical", "multi", "data", "uncond", "no", "none:geometry predicate", when="ar")
s("prt-prp.f90:1175", "release point in IDOMAIN<=0 cell", "K7", "logical", "multi", "data", "uncond", "partly", "FK(active cell)")
s("prt-prp.f90:1182", "LOCAL_Z in [0,1]", "K2", "logical", "field", "data", "opt:local_z(logical)", "no", "CHECK(conditional)")
s("prt-prp.f90:1261", "RELEASETIMES block required when NRELEASETIMES>0", "K4", "logical", "component", "cfg-data", "dim", "no", "CHECK(count(*)=dim)")
s("prt-prp.f90:1279", "release times strictly increase", "K9", "logical", "table", "data", "uncond", "no", "none:ordered rows")
s("prt-prp.f90:496", "release time after end of simulation", "K9", "logical", "multi", "data", "opt:extend_tracking(logical)", "no", "assertion:cross-component", sev="w", when="ar")

# ---- SWF/CHF ----------------------------------------------------------------------------------
s("swf-cxs.f90:384", "IFNO out of 1..NSECTIONS", "K7", "logical", "row", "data", "dim", "yes", "FK")
s("swf-cxs.f90:394", "NXSPOINTS > 1", "K2", "logical", "field", "data", "uncond", "no", "CHECK")
s("swf-cxs.f90:515", "CROSSSECTIONDATA rows not grouped as PACKAGEDATA implies", "K1", "layout", "table", "data", "uncond", "no", "none:row order")
s("swf-dfw.f90:1350", "velocity needs ANGLDEGX", "K4", "logical", "multi", "data", "opt:save_velocity(output)", "no", "assertion:cross-component", when="ar")
s("doc:olf/dfw.tex", "DFW required for each OLF model", "K8", "logical", "multi", "config", "uncond", "no", "assertion:exists")

# ---- TS / TAS / OBS / OC -------------------------------------------------------------------------
s("TimeSeries.f90:1182", "METHODS does not cover all series", "K3", "logical", "row", "config", "uncond", "partly", "CHECK(count)")
s("TimeSeries.f90:552", "series does not cover the integration interval", "K9", "logical", "multi", "data", "binding", "no", "assertion:cross-component", when="ad")
s("TimeSeriesManager.f90:113", "duplicate time-series file name", "K6", "logical", "table", "config", "uncond", "no", "UNIQUE")
s("TimeSeriesManager.f90:564", "value neither number nor TS name", "K7", "logical", "field", "data", "binding", "partly", "FK(union: number|TS name)", when="rp")
s("TimeArraySeriesManager.f90:304", "time-array series not found", "K7", "logical", "multi", "data", "binding", "partly", "FK")
s("doc:gwf/tsi.tex", "a TAS file belongs to one package", "K6", "logical", "multi", "config", "uncond", "no", "UNIQUE")
s("Obs.f90:874", "observation type not found", "K2", "logical", "field", "data", "binding", "yes", "CHECK(in, by target type)")
s("Obs.f90:1000", "OBS outfile provided more than once", "K6", "logical", "table", "config", "uncond", "no", "UNIQUE")
s("gwf-lak.f90:5208", "integer ID but ID2 missing", "K4", "logical", "row", "data", "opt:obstype", "no", "CHECK(row)")
s("gwf-csub.f90:7316", "BOUNDNAME not allowed for this obstype", "K4", "logical", "row", "data", "opt:obstype", "partly", "CHECK(row)")
s("OutputControlData.f90:73", "SAVE requested but no save file", "K5", "output", "component", "config", "opt:save(output)", "no", "CHECK(row)")
s("doc:prt/fmi.tex", "GWF OC must SAVE BUDGET ALL for PRT", "K8", "output", "multi", "config", "binding", "no", "none:external run")

out = sys.argv[1]
with open(os.path.join(out, "mf6-sample.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(S[0]))
    w.writeheader()
    w.writerows(S)

C = collections.Counter
print(len(S), "labelled instances")
kinds = sorted({r["kind"] for r in S}, key=lambda k: (len(k), k))
print(f"{'kind':5} {'n':>3}  level                       dfn(yes/partly/no)  arity(top)        cd")
for k in kinds:
    rs = [r for r in S if r["kind"] == k]
    lv = dict(C(r["level"] for r in rs))
    dfn = C(r["dfn"] for r in rs)
    ar = C(r["arity"] for r in rs).most_common(2)
    cd = dict(C(r["cd"] for r in rs))
    print(f"{k:5} {len(rs):3}  {str(lv):27} {dfn['yes']}/{dfn['partly']}/{dfn['no']:<14} {str(ar):18} {cd}")
print("\nlevel x trigger-class:")
def tclass(t):
    if t.startswith("opt:"):
        lab = t[t.find("(") + 1:-1] if "(" in t else "?"
        return "opt:" + lab.split("/")[0]
    return t.split(":")[0]
print(dict(C((r["level"], tclass(r["trigger"])) for r in S)))
print("\nwhen:", dict(C(r["when"] for r in S)), " sev:", dict(C(r["sev"] for r in S)))
print("arity multi/sim share:", sum(r["arity"] in ("multi", "sim") for r in S), "/", len(S))
print("ddl:", dict(C(r["ddl"].split("(")[0].split(":")[0] for r in S)))
print("none reasons:", dict(C(r["ddl"].split(":", 1)[1] for r in S if r["ddl"].startswith("none"))))
print("prose-only:", [r["site"] for r in S if r["site"].startswith("doc:")])
