package registry;

import model.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;


public class TwinRegistry {

    private Map<String, TwinEntity> entities = new HashMap<>();
    private Map<String, TwinComponent> components = new HashMap<>();
    private Map<String, TwinStrategy> strategies = new HashMap<>();
    private Map<String,TwinComponentProperty> properties = new HashMap<>();


    public void registerEntity(String id, TwinEntity entity) {
        entities.put(id, entity);
    }

    public void registerComponent(String id, TwinComponent component) {
        components.put(id, component);
    }

    public void registerStrategy(String id, TwinStrategy strategy) {
        strategies.put(id, strategy);
    }

    public void registerProperty(TwinComponent component, TwinComponentProperty property) throws IllegalStateException {
        if(propertyExists(component.getId(),property.getPropertyGuid())){
            TwinComponentProperty existingProperty = properties.get(component.getId()+property.getPropertyGuid());
            throw new IllegalStateException(
                    String.format("Failed to connect Property {%s} with component {%s} and device {%s}\n" +
                            "Property {%s} from component {%s} is already measured by device {%s}",
                            property.getName(),
                            component.getParentEntity().getEntityName(),
                            component.getComponentName(),

                            property.getName(),
                            existingProperty.getComponent().getParentEntity().getEntityName(),
                            existingProperty.getComponent().getComponentName()));
        }
        property.setComponent(component);
        property.attachToParent();
        properties.put(component.getId()+property.getPropertyGuid(), property);
    }
    public void registerProperty(String componentId, String propertyName, TwinComponentProperty property) {
        if(propertyExists(componentId,propertyName)){
            throw new IllegalStateException();
        }
        properties.put(componentId+propertyName, property);
    }
    public boolean propertyExists(String entityId, String componentId, String propertyName) {
        return properties.containsKey(entityId + componentId + propertyName);
    }



    public TwinEntity getEntity(String id) {
        return entities.get(id);
    }

    public TwinComponent getComponent(String id) {
        return components.get(id);
    }

    public TwinStrategy getStrategy(String id) {
        return strategies.get(id);
    }


    public TwinComponentProperty getConstProperty(String componentId, String id) {
        return properties.get(componentId+id);
    }

    public TwinComponentProperty getProperty(String entityId,String componentId, String id) {
        return properties.get(entityId+componentId+id);

    }

    public boolean propertyExists(String componentId,String propertyName) {
        return properties.containsKey(componentId+propertyName);
    }


    public List<TwinEntity> getTwins() {
        return entities.values().stream().toList();
    }
}


