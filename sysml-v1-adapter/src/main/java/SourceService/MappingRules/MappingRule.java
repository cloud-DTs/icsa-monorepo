package SourceService.MappingRules;

import SourceService.SourceXMIElements.StereotypeElement;
import SourceService.XMIContext;
import lombok.Getter;
import registry.TwinRegistry;

@Getter
public abstract class MappingRule<T extends  StereotypeElement> {

    private XMIContext xmiContext;
    private TwinRegistry twinRegistry;

    public MappingRule(XMIContext xmiContext, TwinRegistry twinRegistry) {
        this.xmiContext = xmiContext;
        this.twinRegistry = twinRegistry;
    }

    public abstract boolean matches(T element);
    public abstract void apply(T element);
}

