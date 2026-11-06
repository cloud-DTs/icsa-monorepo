package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.AbstractType;
import org.example.Model.DTCore;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.Type;

import java.util.List;

public class TwinAttributeCore extends DTCore {

	public TwinAttributeCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected void fillDTSlots(AbstractType<?, ?> owner, List<Feature> features) {
	}
}
