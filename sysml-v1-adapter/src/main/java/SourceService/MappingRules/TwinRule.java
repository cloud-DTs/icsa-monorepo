package SourceService.MappingRules;

import SourceService.SourceXMIElements.Element.EAElement;
import SourceService.SourceXMIElements.Mapper.Stereotypes;
import SourceService.XMIContext;
import model.TwinDataBase;
import model.TwinEntity;
import registry.TwinRegistry;

import java.util.List;
import java.util.UUID;

public class TwinRule extends MappingRule<EAElement> {

    public TwinRule(XMIContext xmiContext, TwinRegistry twinRegistry) {
        super(xmiContext,twinRegistry);
    }

    @Override
    public boolean matches(EAElement element) {
        return element.getStereotypeName().equals(Stereotypes.TWIN);
    }

    @Override
    public void apply(EAElement element) {
        if(element.getIdref() == null){
            return;
        }
        addTwinAsEntity(element);
    }

    private void addTwinAsEntity(EAElement element) {
        TwinEntity twinEntity = new TwinEntity();
        twinEntity.setEntityId(element.getIdref());
        twinEntity.setEntityName(element.getName());
        twinEntity.setDefinitionId(element.getIdref());

        DatabasePair databasePair = buildDatabases(element);
        twinEntity.setCold(databasePair.cold);
        twinEntity.setHot(databasePair.hot);
        getTwinRegistry().registerEntity(element.getIdref(),twinEntity);
    }


    private DatabasePair buildDatabases(EAElement twinElement) {

        List<EAElement> databaseInstances = getXmiContext().getElementsByOwner(
                SourceService.SourceXMIElements.Mapper.Stereotypes.DATABASE_INSTANCE,
                twinElement.getIdref()
        );

        int count = databaseInstances.size();

        if (count == 0) {
            TwinDataBase hot = createDefaultDatabase("HOT");
            TwinDataBase cold = createDefaultDatabase("COLD");
            return new DatabasePair(hot, cold);
        }
        if (count == 1) {
            EAElement existing = databaseInstances.get(0);
            TwinDataBase parsed = buildSingleDatabase(existing);

            boolean isHot = getTier(existing).contains("HOT");

            TwinDataBase fallback = createDefaultDatabase(isHot ? "COLD" : "HOT");

            return isHot
                    ? new DatabasePair(parsed, fallback)  // parsed = HOT
                    : new DatabasePair(fallback, parsed); // parsed = COLD
        }

        if (count == 2) {

            EAElement db1 = databaseInstances.get(0);
            EAElement db2 = databaseInstances.get(1);

            TwinDataBase tdb1 = buildSingleDatabase(db1);
            TwinDataBase tdb2 = buildSingleDatabase(db2);

            boolean db1IsHot = getTier(db1).contains("HOT");
            boolean db2IsHot = getTier(db2).contains("HOT");

            if (db1IsHot && !db2IsHot) {
                return new DatabasePair(tdb1, tdb2);
            }

            if (!db1IsHot && db2IsHot) {
                return new DatabasePair(tdb2, tdb1);
            }

            throw new IllegalStateException(
                    String.format("Twin '%s' must have exactly one HOT and one COLD database", twinElement.getName())
            );
        }

        throw new IllegalStateException(
                String.format("Twin '%s' cannot have %d database instances. Expected 0, 1, or 2.",
                        twinElement.getName(), count)
        );
    }

    private TwinDataBase buildSingleDatabase(EAElement dbInstance) {
        EAElement def = getXmiContext().findDefinitonBlockForInstance(dbInstance);

        TwinDataBase db = new TwinDataBase();
        db.setDataBaseId(dbInstance.getIdref());
        db.setDefinitionId(def.getIdref());
        db.setRetentionDays(getRetentionDays(dbInstance));
        return db;
    }

    private TwinDataBase createDefaultDatabase(String tier) {
        TwinDataBase db = new TwinDataBase();
        db.setDataBaseId(UUID.randomUUID().toString());
        db.setDefinitionId("DEFAULT_" + tier + "_DATABASE");
        db.setRetentionDays("60");
        return db;
    }


    private String getRetentionDays(EAElement db2) {
        return getXmiContext().getTaggedValue(db2,"retentionPeriod");
    }

    private String getTier(EAElement databaseElement){

        return getXmiContext().getTaggedValue(databaseElement,"dataBaseTier");
    }
    private static class DatabasePair {
        final TwinDataBase hot;
        final TwinDataBase cold;

        DatabasePair(TwinDataBase hot, TwinDataBase cold) {
            this.hot = hot;
            this.cold = cold;
        }
    }
}
