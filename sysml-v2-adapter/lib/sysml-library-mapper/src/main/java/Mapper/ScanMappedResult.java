package Mapper;

import lombok.Getter;
import org.omg.sysml.lang.sysml.Type;

import java.util.HashMap;
import java.util.Map;

public class ScanMappedResult {

	@Getter private Map<String ,MappedLibraryTypeInfo> standardinfos = new HashMap<>();
	@Getter private Map<Class<? extends Type>,MetaclassInfo<?>> metaclassinfos = new HashMap<>();



}
