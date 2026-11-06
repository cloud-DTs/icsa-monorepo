package org.example.Model.Enums;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.EmptyCore;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::FeedbackTopicType", core = EmptyCore.class)
public class EnumFeedbackTopicTypeUsage extends EnumAttributeUsage<EnumFeedbackTopicType> {
	public EnumFeedbackTopicTypeUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected Class<EnumFeedbackTopicType> getEnumClass() {
		return EnumFeedbackTopicType.class;
	}
}
