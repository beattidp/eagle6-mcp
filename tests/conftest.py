"""Pytest fixtures providing minimal valid EAGLE v6.6.0 XML documents."""

from __future__ import annotations

from pathlib import Path

import pytest


SAMPLE_LBR_XML = """<?xml version="1.0" encoding="utf-8"?>
<eagle version="6.6.0">
<drawing>
  <layers>
    <layer number="1" name="Top" color="4" fill="1" visible="yes" active="yes"/>
    <layer number="16" name="Bottom" color="1" fill="1" visible="yes" active="yes"/>
  </layers>
  <library>
    <description>Sample test library</description>
    <packages>
      <package name="0805">
        <smd name="1" x="-0.95" y="0" dx="1.0" dy="1.3" layer="1"/>
        <smd name="2" x="0.95" y="0" dx="1.0" dy="1.3" layer="1"/>
      </package>
      <package name="DIP8">
        <pad name="1" x="-3.81" y="-3.81" drill="0.8" diameter="1.6" shape="square"/>
        <pad name="2" x="-1.27" y="-3.81" drill="0.8" diameter="1.6"/>
        <pad name="3" x="1.27" y="-3.81" drill="0.8" diameter="1.6"/>
        <pad name="4" x="3.81" y="-3.81" drill="0.8" diameter="1.6"/>
        <hole x="0" y="0" drill="3.2"/>
      </package>
    </packages>
    <symbols>
      <symbol name="R">
        <pin name="1" x="-5.08" y="0" direction="pas" length="short"/>
        <pin name="2" x="5.08" y="0" direction="pas" length="short" rot="R180"/>
      </symbol>
      <symbol name="MCU4">
        <pin name="VCC" x="-7.62" y="2.54" direction="pwr"/>
        <pin name="GND" x="-7.62" y="-2.54" direction="pwr"/>
        <pin name="IO0" x="7.62" y="2.54" direction="io" rot="R180"/>
        <pin name="NC1" x="7.62" y="-2.54" direction="nc" rot="R180"/>
      </symbol>
      <symbol name="GND">
        <pin name="GND" x="0" y="2.54" direction="sup" rot="R270"/>
      </symbol>
    </symbols>
    <devicesets>
      <deviceset name="R-0805" prefix="R" uservalue="yes">
        <gates><gate name="G$1" symbol="R" x="0" y="0"/></gates>
        <devices>
          <device name="" package="0805">
            <connects>
              <connect gate="G$1" pin="1" pad="1"/>
              <connect gate="G$1" pin="2" pad="2"/>
            </connects>
          </device>
        </devices>
      </deviceset>
      <deviceset name="MCU" prefix="U" uservalue="no">
        <gates><gate name="G$1" symbol="MCU4" x="0" y="0"/></gates>
        <devices>
          <device name="" package="DIP8">
            <connects>
              <connect gate="G$1" pin="VCC" pad="1"/>
              <connect gate="G$1" pin="GND" pad="2"/>
              <connect gate="G$1" pin="IO0" pad="3"/>
              <connect gate="G$1" pin="NC1" pad="4"/>
            </connects>
          </device>
        </devices>
      </deviceset>
      <deviceset name="GND" prefix="GND">
        <gates><gate name="1" symbol="GND" x="0" y="0"/></gates>
        <devices><device name=""/></devices>
      </deviceset>
    </devicesets>
  </library>
</drawing>
</eagle>
"""

SAMPLE_SCH_XML = """<?xml version="1.0" encoding="utf-8"?>
<eagle version="6.6.0">
<drawing>
  <layers>
    <layer number="91" name="Nets" color="2" fill="1" visible="yes" active="yes"/>
  </layers>
  <schematic>
    <libraries>
      <library name="testlib">
        <packages>
          <package name="0805">
            <smd name="1" x="-0.95" y="0" dx="1.0" dy="1.3" layer="1"/>
            <smd name="2" x="0.95" y="0" dx="1.0" dy="1.3" layer="1"/>
          </package>
          <package name="DIP8">
            <pad name="1" x="-3.81" y="-3.81" drill="0.8" diameter="1.6"/>
            <pad name="2" x="-1.27" y="-3.81" drill="0.8" diameter="1.6"/>
            <pad name="3" x="1.27" y="-3.81" drill="0.8" diameter="1.6"/>
            <pad name="4" x="3.81" y="-3.81" drill="0.8" diameter="1.6"/>
          </package>
        </packages>
        <symbols>
          <symbol name="R">
            <pin name="1" x="-5.08" y="0" direction="pas"/>
            <pin name="2" x="5.08" y="0" direction="pas"/>
          </symbol>
          <symbol name="MCU4">
            <pin name="VCC" x="-7.62" y="2.54" direction="pwr"/>
            <pin name="GND" x="-7.62" y="-2.54" direction="pwr"/>
            <pin name="IO0" x="7.62" y="2.54" direction="io"/>
            <pin name="NC1" x="7.62" y="-2.54" direction="nc"/>
          </symbol>
          <symbol name="GND">
            <pin name="GND" x="0" y="2.54" direction="sup"/>
          </symbol>
        </symbols>
        <devicesets>
          <deviceset name="R-0805" prefix="R" uservalue="yes">
            <gates><gate name="G$1" symbol="R" x="0" y="0"/></gates>
            <devices>
              <device name="" package="0805">
                <connects>
                  <connect gate="G$1" pin="1" pad="1"/>
                  <connect gate="G$1" pin="2" pad="2"/>
                </connects>
              </device>
            </devices>
          </deviceset>
          <deviceset name="MCU" prefix="U" uservalue="no">
            <gates><gate name="G$1" symbol="MCU4" x="0" y="0"/></gates>
            <devices>
              <device name="" package="DIP8">
                <connects>
                  <connect gate="G$1" pin="VCC" pad="1"/>
                  <connect gate="G$1" pin="GND" pad="2"/>
                  <connect gate="G$1" pin="IO0" pad="3"/>
                  <connect gate="G$1" pin="NC1" pad="4"/>
                </connects>
              </device>
            </devices>
          </deviceset>
          <deviceset name="GND" prefix="GND">
            <gates><gate name="1" symbol="GND" x="0" y="0"/></gates>
            <devices><device name=""/></devices>
          </deviceset>
        </devicesets>
      </library>
    </libraries>
    <classes>
      <class number="0" name="default" width="0.254" drill="0.3"/>
      <class number="1" name="power" width="0.508" drill="0.4"/>
    </classes>
    <parts>
      <part name="R1" library="testlib" deviceset="R-0805" device="" value="10k">
        <attribute name="MPN" value="RC0805FR-0710KL"/>
      </part>
      <part name="R2" library="testlib" deviceset="R-0805" device=""/>
      <part name="U1" library="testlib" deviceset="MCU" device=""/>
      <part name="GND1" library="testlib" deviceset="GND" device=""/>
    </parts>
    <sheets>
      <sheet>
        <instances>
          <instance part="R1" gate="G$1" x="10" y="10"/>
          <instance part="R2" gate="G$1" x="20" y="10"/>
          <instance part="U1" gate="G$1" x="40" y="20"/>
          <instance part="GND1" gate="1" x="40" y="5"/>
        </instances>
        <nets>
          <net name="VCC" class="1">
            <segment>
              <pinref part="R1" gate="G$1" pin="1"/>
              <pinref part="U1" gate="G$1" pin="VCC"/>
              <label x="15" y="15" size="1.778" layer="95"/>
            </segment>
          </net>
          <net name="GND" class="1">
            <segment>
              <pinref part="U1" gate="G$1" pin="GND"/>
              <pinref part="GND1" gate="1" pin="GND"/>
            </segment>
          </net>
          <net name="N$1" class="0">
            <segment>
              <pinref part="R1" gate="G$1" pin="2"/>
            </segment>
          </net>
        </nets>
      </sheet>
    </sheets>
  </schematic>
</drawing>
</eagle>
"""

SAMPLE_BRD_XML = """<?xml version="1.0" encoding="utf-8"?>
<eagle version="6.6.0">
<drawing>
  <layers>
    <layer number="1" name="Top" color="4" fill="1" visible="yes" active="yes"/>
    <layer number="16" name="Bottom" color="1" fill="1" visible="yes" active="yes"/>
    <layer number="19" name="Unrouted" color="6" fill="1" visible="yes" active="yes"/>
    <layer number="20" name="Dimension" color="15" fill="1" visible="yes" active="yes"/>
  </layers>
  <board>
    <plain>
      <wire x1="0" y1="0" x2="50" y2="0" width="0" layer="20"/>
      <wire x1="50" y1="0" x2="50" y2="30" width="0" layer="20"/>
      <wire x1="50" y1="30" x2="0" y2="30" width="0" layer="20"/>
      <wire x1="0" y1="30" x2="0" y2="0" width="0" layer="20"/>
      <hole x="3" y="3" drill="3.2"/>
    </plain>
    <libraries>
      <library name="testlib">
        <packages>
          <package name="0805">
            <smd name="1" x="-0.95" y="0" dx="1.0" dy="1.3" layer="1"/>
            <smd name="2" x="0.95" y="0" dx="1.0" dy="1.3" layer="1"/>
          </package>
          <package name="DIP8">
            <pad name="1" x="-3.81" y="-3.81" drill="0.8" diameter="1.6"/>
            <pad name="2" x="-1.27" y="-3.81" drill="0.8" diameter="1.6"/>
          </package>
        </packages>
      </library>
    </libraries>
    <classes>
      <class number="0" name="default" width="0.254" drill="0.3"/>
      <class number="1" name="power" width="0.508" drill="0.4"/>
    </classes>
    <designrules name="default">
      <param name="layerSetup" value="(1*16)"/>
      <param name="mdWireWire" value="8mil"/>
      <param name="msWidth" value="8mil"/>
      <param name="msDrill" value="12mil"/>
    </designrules>
    <elements>
      <element name="R1" library="testlib" package="0805" value="10k" x="10" y="15" rot="R90"/>
      <element name="R2" library="testlib" package="0805" value="R-0805" x="20" y="15" rot="MR0"/>
      <element name="U1" library="testlib" package="DIP8" value="MCU" x="35" y="15" rot="R0"/>
    </elements>
    <signals>
      <signal name="VCC" class="1">
        <contactref element="R1" pad="1"/>
        <contactref element="U1" pad="1"/>
        <wire x1="10" y1="15" x2="31.19" y2="15" width="0.508" layer="1"/>
        <via x="25" y="15" extent="1-16" drill="0.4" diameter="0.8"/>
      </signal>
      <signal name="GND" class="1">
        <contactref element="U1" pad="2"/>
        <wire x1="33.73" y1="11.19" x2="40" y2="11.19" width="0" layer="19" extent="1-1"/>
      </signal>
      <signal name="N$1" class="0">
        <contactref element="R1" pad="2"/>
      </signal>
    </signals>
  </board>
</drawing>
</eagle>
"""

SAMPLE_DRU = """description[en] = Test DRU rules
layerSetup = (1*16)
mdWireWire = 6mil
msWidth = 0.15mm
msDrill = 10mil
"""


@pytest.fixture()
def sample_project_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with matching .sch, .brd, .lbr, and .dru files."""
    (tmp_path / "demo.sch").write_text(SAMPLE_SCH_XML, encoding="utf-8")
    (tmp_path / "demo.brd").write_text(SAMPLE_BRD_XML, encoding="utf-8")
    (tmp_path / "testlib.lbr").write_text(SAMPLE_LBR_XML, encoding="utf-8")
    (tmp_path / "custom.dru").write_text(SAMPLE_DRU, encoding="utf-8")
    # Also create a fake legacy binary file (0x10 0x00 header)
    (tmp_path / "old_v5.sch").write_bytes(b"\x10\x00\x00\x00legacy binary content")
    return tmp_path
