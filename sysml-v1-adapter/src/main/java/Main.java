import SourceService.Mapper;
import SourceService.XMIParser;
import SourceService.XMIContext;
import TargetService.ConfigDTO;
import TargetService.DeployerCleaner;
import TargetService.DeployerMapper;
import TargetService.DeployerModelDTO;
import com.fasterxml.jackson.databind.ObjectMapper;
import model.TwinEntity;
import org.w3c.dom.Document;
import org.w3c.dom.NodeList;
import registry.TwinRegistry;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;

public class Main {

    public static void main(String[] args) {

        if (args.length != 2) {
            System.err.println("Expected exactly 2 arguments, got " + args.length);
            System.err.println("Argument 1: <PathToXmiFile>");
            System.err.println("Argument 2: <Name of the digital twin>");
            System.exit(1);
            return;
        }

        String fileName = args[0];
        String twinName = args[1].toLowerCase();

        if(twinName.length() > 10){
            throw new IllegalStateException("Twin name has a maximal length of 10 characters. Actual length: "+ twinName.length());
        }

        try {
            File xmiFile = new File(fileName);
            if (!xmiFile.exists()) {
                System.err.println("File not found: " + xmiFile.getAbsolutePath());
                System.exit(1);
                return;
            }

            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            DocumentBuilder builder = factory.newDocumentBuilder();
            Document doc = builder.parse(xmiFile);

            NodeList elements = doc.getElementsByTagName("element");
            NodeList connectors = doc.getElementsByTagName("connector");
            NodeList ownedAttributes = doc.getElementsByTagName("ownedAttribute");

            XMIParser twinParser = new XMIParser();
            twinParser.parse(elements, connectors, ownedAttributes);

            XMIContext XMIContext = new XMIContext(twinParser);
            List<TwinEntity> twinEntities = new Mapper(twinParser,new TwinRegistry(), XMIContext).parse();

            ObjectMapper objectMapper = new ObjectMapper();

            for (TwinEntity twinEntity : twinEntities) {
                DeployerModelDTO deployerModelDTO = DeployerMapper.INSTANCE.toDeployerModelDTO(twinEntity);
                Path entityDir = Paths.get(twinName);
                Files.createDirectories(entityDir);

                ConfigDTO config = getJsonObject(twinName,twinEntity);
                writeJsonFile(objectMapper,entityDir.resolve("config.json").toString(),config);
                writeJsonFile(objectMapper, entityDir.resolve("config_hierarchy.json").toString(),
                        deployerModelDTO.getConfigHierarchy());
                writeJsonFile(objectMapper, entityDir.resolve("config_iot_devices.json").toString(),
                        deployerModelDTO.getConfigIotDevice());
                writeJsonFile(objectMapper, entityDir.resolve("config_events.json").toString(),
                        deployerModelDTO.getConfigEvent());

                DeployerCleaner.clean(entityDir, objectMapper);
            }

        } catch (Exception e) {
            e.printStackTrace();
            System.exit(1);
        }
    }

    private static ConfigDTO getJsonObject(String digitalTwinName,TwinEntity twinEntity) {
        ConfigDTO config = new ConfigDTO();
        config.setDigital_twin_name(digitalTwinName);
        config.setCold_storage_definition_id(twinEntity.getCold().getDefinitionId());
        config.setCold_storage_id(twinEntity.getCold().getId());
        config.setCold_storage_size_in_days(Integer.valueOf(twinEntity.getCold().getRetentionDays()));
        config.setHot_storage_definition_id(twinEntity.getHot().getDefinitionId());
        config.setHot_storage_id(twinEntity.getHot().getId());
        config.setHot_storage_size_in_days(Integer.valueOf(twinEntity.getHot().getRetentionDays()));

        return config;
    }

    private static void writeJsonFile(ObjectMapper mapper, String fileName, Object data) throws Exception {
        try (FileWriter writer = new FileWriter(fileName)) {
            mapper.writerWithDefaultPrettyPrinter().writeValue(writer, data);
        }
    }
}
