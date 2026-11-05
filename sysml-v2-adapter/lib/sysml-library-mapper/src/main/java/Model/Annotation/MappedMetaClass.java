package Model.Annotation;

import Model.Core.Core;
import org.omg.sysml.lang.sysml.Type;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
public @interface MappedMetaClass {
	Class<? extends Type> value();

	// core created by the parser for every instance of the annotated class
	Class<? extends Core<?>> core();
}
