package SourceService.SourceXMIElements;

import lombok.*;
import org.w3c.dom.Element;

@Getter
@Setter
@NoArgsConstructor
@ToString(callSuper = true)
public class Property {
    private String stereoType;

    public static Property parse(Element prop) {
        Property property = new Property();
        if(prop == null){
            property.setStereoType(null);
            return property;
        }

        property.stereoType = prop.getAttribute("stereotype");
        return property;
    }
}

/*
<element xmi:idref="EAID_B7B86097_2DE1_4e68_9E88_B60E0D007AD3" xmi:type="uml:Port" name="S2" scope="public">
				<model package="EAPK_FA4077D2_9A30_41d5_AA26_BC3030CE0FB9" owner="EAID_476732F2_6A22_4099_BA1B_A7A90E2BC0E9" tpos="0" ea_localid="368" ea_eleType="element"/>
				<properties isSpecification="false" sType="Port" nType="0" scope="public" isRoot="false" isLeaf="false" isAbstract="false"/>
				<project author="rsicher" version="1.0" phase="1.0" created="2025-03-12 09:48:01" modified="2025-03-13 11:32:50" complexity="1" status="Proposed"/>
				<code gentype="&lt;none&gt;"/>
				<style appearance="BackColor=-1;BorderColor=-1;BorderWidth=-1;FontColor=-1;VSwimLanes=1;HSwimLanes=1;BorderStyle=0;"/>
				<tags/>
				<xrefs/>
				<extendedProperties tagged="0" package_name="Siemens Technology Emob Testbed" multiplicity="0..1" propertyType="{52F1AA55-2BA2-4ebb-97E8-98EC0EB82FE5}"/>
			</element>
 */