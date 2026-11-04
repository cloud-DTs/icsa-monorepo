package TargetService;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class ConfigDTO {
    private String digital_twin_name;
    private int hot_storage_size_in_days;
    private String hot_storage_id;
    private String hot_storage_definition_id;
    private int cold_storage_size_in_days;
    private String cold_storage_id;
    private String cold_storage_definition_id;

}
