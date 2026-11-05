package Model.Annotation;

import Model.Core.Core;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
public @interface MappedLibrary {
	String libraryName();

	// core created by the parser for every instance of the annotated class
	Class<? extends Core<?>> core();
}
